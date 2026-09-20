package store

import (
	"encoding/json"
	"path/filepath"
)

type Checkpoint struct {
	ID        string    `json:"id"`
	RoundID   string    `json:"round_id"`
	RecordRef RecordRef `json:"record_ref"`
	Created   string    `json:"created"`
}

func (c *Control) Checkpoints() ([]Checkpoint, error) {
	db, err := OpenDB(c.Path)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	rows, err := db.Query("SELECT id,round_id,record_ref,created FROM checkpoints ORDER BY rowid")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Checkpoint{}
	for rows.Next() {
		var v Checkpoint
		var raw string
		if err = rows.Scan(&v.ID, &v.RoundID, &raw, &v.Created); err != nil {
			return nil, err
		}
		if err = json.Unmarshal([]byte(raw), &v.RecordRef); err != nil {
			return nil, err
		}
		out = append(out, v)
	}
	return out, rows.Err()
}
func (c *Control) Checkpoint(id string) (Object, error) {
	db, err := OpenDB(c.Path)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	var raw string
	if err = db.QueryRow("SELECT record_ref FROM checkpoints WHERE id=?", id).Scan(&raw); err != nil {
		return nil, err
	}
	var ref RecordRef
	if err = json.Unmarshal([]byte(raw), &ref); err != nil {
		return nil, err
	}
	body, err := (Records{Directory: filepath.Join(filepath.Dir(c.Path), "records")}).Get(ref)
	if err != nil {
		return nil, err
	}
	return DecodeObject(string(body))
}
