package authority

import (
	"loom/runtime/store"
	"loom/runtime/work"
	"os"
	"path/filepath"
	"sync"
	"testing"
)

func TestDefaultResourceNamesAreStableDistinctAndGrantNothing(t *testing.T) {
	a, w, root := fixture(t)
	first, second := filepath.Join(root, "project-a"), filepath.Join(root, "project-b")
	for _, path := range []string{first, second} {
		if err := os.Mkdir(path, 0700); err != nil {
			t.Fatal(err)
		}
	}
	names := make(chan string, 6)
	var group sync.WaitGroup
	for i := 0; i < 6; i++ {
		group.Add(1)
		go func() {
			defer group.Done()
			name, err := a.NameResource(first)
			if err != nil {
				t.Error(err)
				return
			}
			names <- name
		}()
	}
	group.Wait()
	close(names)
	var saved string
	for name := range names {
		if saved != "" && name != saved {
			t.Fatal("same source split into different identities")
		}
		saved = name
	}
	other, err := a.NameResource(second)
	if err != nil || saved == "" || other == saved {
		t.Fatal(saved, other, err)
	}
	if _, err = a.NameResource(w.Surface); err == nil {
		t.Fatal("named Work files as task resource")
	}
	if err = os.Mkdir(filepath.Join(first, "nested"), 0700); err != nil {
		t.Fatal(err)
	}
	if _, err = a.NameResource(filepath.Join(first, "nested")); err == nil {
		t.Fatal("overlapping source named independently")
	}
	db, err := store.OpenDB(a.Path)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	var grants int
	if err = db.QueryRow("SELECT count(*) FROM resource_grants").Scan(&grants); err != nil || grants != 0 {
		t.Fatal("naming granted Work authority", grants, err)
	}
}

func TestSameResourceGrantedToIndependentWorks(t *testing.T) {
	a, first, root := fixture(t)
	source := filepath.Join(root, "project")
	os.Mkdir(source, 0700)
	os.WriteFile(filepath.Join(source, "initial"), []byte("same"), 0600)
	second, err := work.Create(filepath.Join(root, "second"), first.Harness, filepath.Join(first.Path, "work.toml"))
	if err != nil {
		t.Fatal(err)
	}
	if err = a.Register(second); err != nil {
		t.Fatal(err)
	}
	for _, w := range []*work.Work{first, second} {
		if err = a.Grant(w, source); err != nil {
			t.Fatal(err)
		}
	}
	g1, err := a.Resource(first, "app")
	if err != nil {
		t.Fatal(err)
	}
	g2, err := a.Resource(second, "app")
	if err != nil {
		t.Fatal(err)
	}
	if g1.ID != g2.ID || g1.Scope != g2.Scope {
		t.Fatal("same project acquired Work-specific resource identity")
	}
	c1, err := first.ResourceCopy("app", "default")
	if err != nil {
		t.Fatal(err)
	}
	c2, err := second.ResourceCopy("app", "default")
	if err != nil {
		t.Fatal(err)
	}
	if c1.ID == c2.ID {
		t.Fatal("Works shared writable copy")
	}
	roles1, err := a.ExecutionIdentity(first, 100000, 10000)
	if err != nil {
		t.Fatal(err)
	}
	roles2, err := a.ExecutionIdentity(second, 100000, 10000)
	if err != nil {
		t.Fatal(err)
	}
	if roles1.HarnessUID == roles1.BashUID || roles1.HarnessUID == roles2.HarnessUID || roles1.BashUID == roles2.BashUID {
		t.Fatal("role or Work Unix identity collision")
	}
}
