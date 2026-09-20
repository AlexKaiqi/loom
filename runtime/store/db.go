// Package store is the durable event and control boundary. SQLite owns recovery.
package store

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"

	_ "modernc.org/sqlite"
)

type Object = map[string]any

var ErrConflict = errors.New("conflict")
var ErrUnknownEffect = fmt.Errorf("%w: unresolved effect", ErrConflict)

func Canonical(value any) (string, error) { b, err := json.Marshal(value); return string(b), err }
func Digest(value any) (string, error) {
	s, err := Canonical(value)
	if err != nil {
		return "", err
	}
	hash := sha256.Sum256([]byte(s))
	return hex.EncodeToString(hash[:]), nil
}
func ID() (string, error) {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[:4], b[4:6], b[6:8], b[8:10], b[10:]), nil
}
func DecodeObject(s string) (Object, error) {
	var out Object
	d := json.NewDecoder(strings.NewReader(s))
	d.UseNumber()
	err := d.Decode(&out)
	return out, err
}
func OpenDB(path string) (*sql.DB, error) {
	absolute, err := filepath.Abs(path)
	if err != nil {
		return nil, err
	}
	u := url.URL{Scheme: "file", Path: absolute}
	q := url.Values{}
	q.Add("_pragma", "foreign_keys(1)")
	q.Add("_pragma", "busy_timeout(30000)")
	q.Add("_pragma", "synchronous(FULL)")
	u.RawQuery = q.Encode()
	db, err := sql.Open("sqlite", u.String())
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(4)
	if err = db.Ping(); err != nil {
		db.Close()
		return nil, err
	}
	return db, nil
}
func Immediate(path string, fn func(*sql.Conn) error) error {
	db, err := OpenDB(path)
	if err != nil {
		return err
	}
	defer db.Close()
	conn, err := db.Conn(context.Background())
	if err != nil {
		return err
	}
	defer conn.Close()
	if _, err = conn.ExecContext(context.Background(), "BEGIN IMMEDIATE"); err != nil {
		return err
	}
	defer conn.ExecContext(context.Background(), "ROLLBACK")
	if err = fn(conn); err != nil {
		return err
	}
	_, err = conn.ExecContext(context.Background(), "COMMIT")
	return err
}
func Initialize(path string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return err
	}
	db, err := OpenDB(path)
	if err != nil {
		return err
	}
	defer db.Close()
	if _, err = db.Exec("PRAGMA journal_mode=WAL"); err != nil {
		return err
	}
	_, err = db.Exec(schema)
	return err
}

const schema = `
CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT,source TEXT NOT NULL,request_id TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,digest TEXT NOT NULL,created TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')));
CREATE TABLE admissions(source TEXT NOT NULL,request_id TEXT NOT NULL,digest TEXT NOT NULL,seq INTEGER NOT NULL REFERENCES events(seq),PRIMARY KEY(source,request_id));
CREATE TABLE pending(seq INTEGER PRIMARY KEY REFERENCES events(seq));
CREATE TABLE rounds(id TEXT PRIMARY KEY,owner TEXT NOT NULL,input_seq INTEGER NOT NULL,state TEXT NOT NULL CHECK(state IN('running','paused','completed','rejected')),revision TEXT,error TEXT,checkpoint TEXT,created TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')));
CREATE UNIQUE INDEX one_active_round ON rounds((1)) WHERE state IN('running','paused');
CREATE TABLE effects(id TEXT PRIMARY KEY,round_id TEXT NOT NULL REFERENCES rounds(id),key TEXT NOT NULL,kind TEXT NOT NULL,request TEXT NOT NULL,digest TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN('intent','completed','unknown')),receipt TEXT,result TEXT,error TEXT,UNIQUE(round_id,key));
CREATE TRIGGER immutable_event_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'events are immutable'); END;
CREATE TRIGGER immutable_event_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'events are immutable'); END;
PRAGMA user_version=2;`

type scanner interface{ Scan(...any) error }

func requireOne(result sql.Result, err error) error {
	if err != nil {
		return err
	}
	n, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if n != 1 {
		return fmt.Errorf("%w: record missing or settled", ErrConflict)
	}
	return nil
}
