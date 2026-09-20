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
	"strconv"
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
	db.SetMaxOpenConns(1)
	if err = db.Ping(); err != nil {
		db.Close()
		return nil, err
	}
	if err = verifyDatabase(db); err != nil {
		db.Close()
		return nil, err
	}
	return db, nil
}

// Read back the actual engine and connection settings, rather than trusting a
// driver version or a successfully parsed DSN. Every opened pool has one verified
// connection; replacement connections receive the same explicit DSN pragmas.
func verifyDatabase(db *sql.DB) error {
	var version, mode string
	var full, foreign int
	if err := db.QueryRow("SELECT sqlite_version()").Scan(&version); err != nil {
		return err
	}
	parts := strings.Split(version, ".")
	var v [3]int
	if len(parts) != 3 {
		return errors.New("unrecognized SQLite engine version")
	}
	for i := range parts {
		n, err := strconv.Atoi(parts[i])
		if err != nil {
			return err
		}
		v[i] = n
	}
	fixed := v[0] > 3 || v[0] == 3 && (v[1] > 51 || v[1] == 51 && v[2] >= 3 || v[1] == 50 && v[2] >= 7 || v[1] == 44 && v[2] >= 6)
	if !fixed {
		return fmt.Errorf("SQLite %s lacks the required WAL-reset fix", version)
	}
	if err := db.QueryRow("PRAGMA journal_mode=WAL").Scan(&mode); err != nil {
		return err
	}
	if err := db.QueryRow("PRAGMA synchronous").Scan(&full); err != nil {
		return err
	}
	if err := db.QueryRow("PRAGMA foreign_keys").Scan(&foreign); err != nil {
		return err
	}
	if mode != "wal" || full != 2 || foreign != 1 {
		return errors.New("SQLite requires WAL, FULL synchronous and foreign keys")
	}
	return nil
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
CREATE TABLE round_inputs(round_id TEXT NOT NULL REFERENCES rounds(id),seq INTEGER NOT NULL REFERENCES events(seq),PRIMARY KEY(round_id,seq));
CREATE TABLE allocations(id TEXT PRIMARY KEY,effect_id TEXT NOT NULL REFERENCES effects(id),target TEXT NOT NULL,binding TEXT NOT NULL,sandbox_id TEXT,execution_id TEXT,observation TEXT,release_state TEXT NOT NULL CHECK(release_state IN('pending','confirmed','unknown')));
CREATE TABLE resource_sources(alias TEXT PRIMARY KEY,source TEXT NOT NULL);
CREATE TABLE resource_copies(id TEXT PRIMARY KEY,alias TEXT NOT NULL REFERENCES resource_sources(alias),target TEXT NOT NULL,generation INTEGER NOT NULL,content_ref TEXT NOT NULL,UNIQUE(alias,target));
CREATE TABLE resource_versions(seq INTEGER PRIMARY KEY AUTOINCREMENT,copy_id TEXT NOT NULL REFERENCES resource_copies(id),predecessor TEXT NOT NULL,content_ref TEXT NOT NULL,effect_id TEXT NOT NULL);
CREATE TABLE content_deliveries(effect_id TEXT PRIMARY KEY REFERENCES effects(id),candidate_ref TEXT NOT NULL,revision TEXT);
CREATE TRIGGER immutable_resource_source_update BEFORE UPDATE ON resource_sources BEGIN SELECT RAISE(ABORT,'resource sources are immutable'); END;
CREATE TRIGGER immutable_resource_source_delete BEFORE DELETE ON resource_sources BEGIN SELECT RAISE(ABORT,'resource sources are immutable'); END;
CREATE TRIGGER immutable_resource_version_update BEFORE UPDATE ON resource_versions BEGIN SELECT RAISE(ABORT,'resource versions are immutable'); END;
CREATE TRIGGER immutable_resource_version_delete BEFORE DELETE ON resource_versions BEGIN SELECT RAISE(ABORT,'resource versions are immutable'); END;
CREATE TABLE selected_strategy(singleton INTEGER PRIMARY KEY CHECK(singleton=1),content_ref TEXT NOT NULL);
CREATE TABLE subscriptions(id TEXT PRIMARY KEY,source_work_id TEXT NOT NULL,kinds TEXT NOT NULL,start_seq INTEGER NOT NULL,cursor INTEGER NOT NULL,active INTEGER NOT NULL CHECK(active IN(0,1)));
CREATE TABLE deliveries(subscription_id TEXT NOT NULL REFERENCES subscriptions(id),source_seq INTEGER NOT NULL,source_fact_id TEXT NOT NULL,input_seq INTEGER NOT NULL REFERENCES events(seq),PRIMARY KEY(subscription_id,source_seq));
CREATE TABLE rounds(id TEXT PRIMARY KEY,owner TEXT NOT NULL,input_seq INTEGER NOT NULL,state TEXT NOT NULL CHECK(state IN('ready','running','recovering','blocked','handed_off')),revision TEXT,error TEXT,checkpoint TEXT,created TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')));
CREATE TABLE checkpoints(id TEXT PRIMARY KEY,round_id TEXT NOT NULL REFERENCES rounds(id),owner TEXT NOT NULL,record_ref TEXT NOT NULL,created TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')));
ALTER TABLE rounds ADD COLUMN harness_ref TEXT NOT NULL DEFAULT '';
ALTER TABLE rounds ADD COLUMN epoch INTEGER NOT NULL DEFAULT 1;
CREATE UNIQUE INDEX one_active_round ON rounds((1)) WHERE state IN('ready','running','recovering','blocked');
CREATE TABLE effects(id TEXT PRIMARY KEY,round_id TEXT NOT NULL REFERENCES rounds(id),key TEXT NOT NULL,kind TEXT NOT NULL,request TEXT NOT NULL,digest TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN('intent','completed','unknown')),receipt TEXT,result TEXT,error TEXT,UNIQUE(round_id,key));
ALTER TABLE effects ADD COLUMN dispatch_state TEXT NOT NULL DEFAULT 'prepared' CHECK(dispatch_state IN('prepared','attempted'));
ALTER TABLE effects ADD COLUMN resolution TEXT NOT NULL DEFAULT 'unresolved' CHECK(resolution IN('unresolved','native_result','confirmed_not_executed'));
ALTER TABLE effects ADD COLUMN observation TEXT NOT NULL DEFAULT 'pending' CHECK(observation IN('pending','running','unknown'));
ALTER TABLE effects ADD COLUMN cancellation TEXT NOT NULL DEFAULT 'none' CHECK(cancellation IN('none','requested','stop_confirmed','unknown'));
ALTER TABLE effects ADD COLUMN content_delivery TEXT NOT NULL DEFAULT 'not_required' CHECK(content_delivery IN('not_required','pending','confirmed','failed','unknown'));
CREATE TABLE effect_observations(seq INTEGER PRIMARY KEY AUTOINCREMENT,effect_id TEXT NOT NULL REFERENCES effects(id),kind TEXT NOT NULL,body TEXT NOT NULL);
CREATE TRIGGER immutable_observation_update BEFORE UPDATE ON effect_observations BEGIN SELECT RAISE(ABORT,'observations are immutable'); END;
CREATE TRIGGER immutable_observation_delete BEFORE DELETE ON effect_observations BEGIN SELECT RAISE(ABORT,'observations are immutable'); END;
CREATE TRIGGER immutable_checkpoint_update BEFORE UPDATE ON checkpoints BEGIN SELECT RAISE(ABORT,'checkpoints are immutable'); END;
CREATE TRIGGER immutable_checkpoint_delete BEFORE DELETE ON checkpoints BEGIN SELECT RAISE(ABORT,'checkpoints are immutable'); END;
CREATE TRIGGER immutable_event_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'events are immutable'); END;
CREATE TRIGGER immutable_event_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'events are immutable'); END;
PRAGMA user_version=3;`

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
