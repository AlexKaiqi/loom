package authority

import (
	"fmt"
	"loom/runtime/store"
	"loom/runtime/work"
)

// Works separates failures of an individual registered Work from failure of
// the host registry itself. One missing directory cannot stop other owners.
func (a *Authority) Works(observe func(string, error)) ([]*work.Work, error) {
	db, err := store.OpenDB(a.Path)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	rows, err := db.Query("SELECT id,path FROM works ORDER BY id")
	if err != nil {
		return nil, err
	}
	type entry struct{ id, path string }
	entries := []entry{}
	for rows.Next() {
		var e entry
		if err = rows.Scan(&e.id, &e.path); err != nil {
			rows.Close()
			return nil, err
		}
		entries = append(entries, e)
	}
	if err = rows.Err(); err != nil {
		rows.Close()
		return nil, err
	}
	if err = rows.Close(); err != nil {
		return nil, err
	}
	out := []*work.Work{}
	for _, e := range entries {
		w, err := work.Open(e.path)
		if err == nil && w.ID != e.id {
			err = fmt.Errorf("%w: registered Work identity changed", ErrPermission)
		}
		if err == nil {
			err = a.Authorize(w)
		}
		if err != nil {
			if observe != nil {
				observe(e.id, err)
			}
			continue
		}
		out = append(out, w)
	}
	return out, nil
}

func (a *Authority) WorkByID(id string) (*work.Work, error) {
	db, err := store.OpenDB(a.Path)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	var path string
	if err = db.QueryRow("SELECT path FROM works WHERE id=?", id).Scan(&path); err != nil {
		return nil, err
	}
	w, err := work.Open(path)
	if err != nil {
		return nil, err
	}
	if w.ID != id {
		return nil, ErrPermission
	}
	if err = a.Authorize(w); err != nil {
		return nil, err
	}
	return w, nil
}
