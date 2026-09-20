package authority

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"loom/runtime/store"
	"loom/runtime/work"
)

type ResourceGrant struct {
	Scope  string `json:"resource_scope"`
	ID     string `json:"resource_id"`
	Alias  string `json:"alias"`
	Access string `json:"access"`
	Path   string `json:"-"`
}

// NameResource gives the installation template a portable logical resource
// name. Reusing the same physical source reuses its existing identity; different
// projects never collide just because both templates use the alias "app".
// This does not grant any Work access or capture task content.
func (a *Authority) NameResource(directory string) (string, error) {
	identity, err := StatIdentity(directory)
	if err != nil {
		return "", err
	}
	var name string
	err = store.Immediate(a.Path, func(db *sql.Conn) error {
		ctx := context.Background()
		if contains(identity.Path, a.Path) {
			return fmt.Errorf("%w: resource contains authority", ErrPermission)
		}
		if err := checkOverlap(db, identity, "SELECT path,device,inode FROM works"); err != nil {
			return err
		}
		err := db.QueryRowContext(ctx, "SELECT name FROM resources WHERE path=? AND device=? AND inode=?", identity.Path, identity.Device, identity.Inode).Scan(&name)
		if err == nil {
			return nil
		}
		if !errors.Is(err, sql.ErrNoRows) {
			return err
		}
		if err = checkOverlap(db, identity, "SELECT path,device,inode FROM resources"); err != nil {
			return err
		}
		id, err := store.ID()
		if err != nil {
			return err
		}
		name = "resource-" + id
		_, err = db.ExecContext(ctx, "INSERT INTO resources VALUES(?,?,?,?,?)", id, name, identity.Path, identity.Device, identity.Inode)
		return err
	})
	return name, err
}

func singleAlias(w *work.Work) (string, error) {
	if len(w.Definition.Userspaces) != 1 {
		return "", errors.New("select a resource alias explicitly")
	}
	for alias := range w.Definition.Userspaces {
		return alias, nil
	}
	return "", errors.New("resource not declared")
}
func (a *Authority) Grant(w *work.Work, directory string) error {
	alias, err := singleAlias(w)
	if err != nil {
		return err
	}
	return a.GrantResource(w, alias, directory)
}
func (a *Authority) GrantResource(w *work.Work, alias, directory string) error {
	declaration, ok := w.Definition.Userspaces[alias]
	if !ok {
		return errors.New("unknown Work resource alias")
	}
	target, err := StatIdentity(directory)
	if err != nil {
		return err
	}
	return store.Immediate(a.Path, func(db *sql.Conn) error {
		ctx := context.Background()
		if err := a.authorize(db, w); err != nil {
			return err
		}
		rounds, err := w.Control.Rounds()
		if err != nil {
			return err
		}
		for _, round := range rounds {
			if round.State == "running" {
				current, e := a.resource(db, w, alias)
				if e != nil || current.Path != target.Path {
					return errors.New("baseline_conflict: cannot rebind resource during an active Round")
				}
			}
		}
		if contains(target.Path, a.Path) {
			return fmt.Errorf("%w: resource contains authority", ErrPermission)
		}
		if err := checkOverlap(db, target, "SELECT path,device,inode FROM works"); err != nil {
			return err
		}
		var id string
		var prior Identity
		err = db.QueryRowContext(ctx, "SELECT id,path,device,inode FROM resources WHERE name=?", declaration.Resource).Scan(&id, &prior.Path, &prior.Device, &prior.Inode)
		if errors.Is(err, sql.ErrNoRows) {
			// A physical source has one resource identity even when multiple Works use
			// it. Different aliases/names cannot manufacture independent shared writers.
			if err = checkOverlap(db, target, "SELECT path,device,inode FROM resources"); err != nil {
				return err
			}
			id, err = store.ID()
			if err != nil {
				return err
			}
			if _, err = db.ExecContext(ctx, "INSERT INTO resources VALUES(?,?,?,?,?)", id, declaration.Resource, target.Path, target.Device, target.Inode); err != nil {
				return err
			}
		} else if err != nil {
			return err
		} else if prior != target {
			var otherGrants int
			if err = db.QueryRowContext(ctx, "SELECT count(*) FROM resource_grants WHERE resource_id=? AND (work_id!=? OR alias!=?)", id, w.ID, alias).Scan(&otherGrants); err != nil {
				return err
			}
			if otherGrants != 0 {
				return fmt.Errorf("%w: resource is granted to another Work; granting cannot rebind it", store.ErrConflict)
			}
			if err = checkOverlap(db, target, "SELECT path,device,inode FROM resources WHERE id!=?", id); err != nil {
				return err
			}
			if _, err = db.ExecContext(ctx, "UPDATE resources SET path=?,device=?,inode=? WHERE id=?", target.Path, target.Device, target.Inode, id); err != nil {
				return err
			}
		}
		if _, err = w.BindResource(alias, target.Path); err != nil {
			return err
		}
		verified, err := StatIdentity(target.Path)
		if err != nil {
			return err
		}
		if verified != target {
			return errors.New("resource changed while granting")
		}
		_, err = db.ExecContext(ctx, "INSERT INTO resource_grants VALUES(?,?,?,?) ON CONFLICT(work_id,alias) DO UPDATE SET resource_id=excluded.resource_id,access=excluded.access", w.ID, alias, id, declaration.Access)
		return err
	})
}
func (a *Authority) resource(db interface {
	QueryRowContext(context.Context, string, ...any) *sql.Row
}, w *work.Work, alias string) (ResourceGrant, error) {
	var g ResourceGrant
	var identity Identity
	var name string
	g.Alias = alias
	err := db.QueryRowContext(context.Background(), "SELECT authority_identity.scope,r.id,g.access,r.path,r.device,r.inode,r.name FROM resource_grants g JOIN resources r ON r.id=g.resource_id CROSS JOIN authority_identity WHERE g.work_id=? AND g.alias=?", w.ID, alias).Scan(&g.Scope, &g.ID, &g.Access, &identity.Path, &identity.Device, &identity.Inode, &name)
	if err != nil {
		return g, fmt.Errorf("%w: resource %s is not granted on this host", ErrPermission, alias)
	}
	current, err := StatIdentity(identity.Path)
	if err != nil || current != identity {
		return g, fmt.Errorf("%w: physical resource changed; explicit regrant required", ErrPermission)
	}
	requested, ok := w.Definition.Userspaces[alias]
	if !ok || requested.Access != g.Access || requested.Resource != name {
		return g, fmt.Errorf("%w: resource grant differs from declaration", ErrPermission)
	}
	g.Path = identity.Path
	return g, nil
}
func (a *Authority) Resource(w *work.Work, alias string) (ResourceGrant, error) {
	db, err := store.OpenDB(a.Path)
	if err != nil {
		return ResourceGrant{}, err
	}
	defer db.Close()
	if err = a.authorize(db, w); err != nil {
		return ResourceGrant{}, err
	}
	return a.resource(db, w, alias)
}
