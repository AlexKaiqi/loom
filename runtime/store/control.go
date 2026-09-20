package store

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"path/filepath"
	"strconv"
)

type Round struct {
	ID         string `json:"id"`
	Owner      string `json:"owner"`
	InputSeq   int64  `json:"input_seq,string"`
	State      string `json:"state"`
	Revision   string `json:"revision,omitempty"`
	Error      string `json:"error,omitempty"`
	Checkpoint Object `json:"checkpoint,omitempty"`
	Created    string `json:"created"`
	HarnessRef string `json:"harness_ref"`
	Epoch      int64  `json:"epoch,string"`
}
type Effect struct {
	ID              string `json:"id"`
	RoundID         string `json:"round_id"`
	Key             string `json:"key"`
	Kind            string `json:"kind"`
	Request         Object `json:"request"`
	Digest          string `json:"digest"`
	Status          string `json:"status"`
	Receipt         Object `json:"receipt"`
	Result          Object `json:"result"`
	Error           string `json:"error,omitempty"`
	DispatchState   string `json:"dispatch_state"`
	Resolution      string `json:"resolution"`
	Observation     string `json:"observation"`
	Cancellation    string `json:"cancellation"`
	ContentDelivery string `json:"content_delivery"`
}
type Control struct {
	Path           string
	RoundID, Owner string
	Epoch          int64
}

func scanRound(row scanner) (Round, error) {
	var r Round
	var rev, msg, cp sql.NullString
	err := row.Scan(&r.ID, &r.Owner, &r.InputSeq, &r.State, &rev, &msg, &cp, &r.Created, &r.HarnessRef, &r.Epoch)
	if err != nil {
		return r, err
	}
	r.Revision, r.Error = rev.String, msg.String
	if cp.Valid {
		r.Checkpoint, err = DecodeObject(cp.String)
	}
	return r, err
}
func scanEffect(row scanner) (Effect, error) {
	var e Effect
	var request string
	var receipt, result, msg sql.NullString
	err := row.Scan(&e.ID, &e.RoundID, &e.Key, &e.Kind, &request, &e.Digest, &e.Status, &receipt, &result, &msg, &e.DispatchState, &e.Resolution, &e.Observation, &e.Cancellation, &e.ContentDelivery)
	if err != nil {
		return e, err
	}
	e.Error = msg.String
	e.Request, err = DecodeObject(request)
	if err != nil {
		return e, err
	}
	if receipt.Valid {
		e.Receipt, err = DecodeObject(receipt.String)
		if err != nil {
			return e, err
		}
	}
	if result.Valid {
		e.Result, err = DecodeObject(result.String)
	}
	return e, err
}
func (c *Control) BeginRound(owner string) (Round, error) {
	return c.BeginRoundSelected(owner, "")
}

// Expected binds preflight authorization to the exact selection atomically
// adopted by this Round. A concurrent management selection must retry preflight.
func (c *Control) BeginRoundSelected(owner, expected string) (Round, error) {
	var r Round
	if owner == "" {
		return r, errors.New("owner required")
	}
	err := Immediate(c.Path, func(db *sql.Conn) error {
		ctx := context.Background()
		if expected != "" {
			var selected string
			if err := db.QueryRowContext(ctx, "SELECT content_ref FROM selected_strategy WHERE singleton=1").Scan(&selected); err != nil {
				return err
			}
			if selected != expected {
				return fmt.Errorf("%w: strategy changed during authorization", ErrConflict)
			}
		}
		var n int
		if err := db.QueryRowContext(ctx, "SELECT count(*) FROM rounds WHERE state IN('ready','running','recovering','blocked')").Scan(&n); err != nil {
			return err
		}
		if n != 0 {
			return fmt.Errorf("%w: active or paused Round exists", ErrConflict)
		}
		var boundary sql.NullInt64
		if err := db.QueryRowContext(ctx, "SELECT MAX(seq) FROM pending").Scan(&boundary); err != nil {
			return err
		}
		if !boundary.Valid {
			return fmt.Errorf("%w: no pending responsibility", ErrConflict)
		}
		id, err := ID()
		if err != nil {
			return err
		}
		if _, err = db.ExecContext(ctx, "INSERT INTO rounds(id,owner,input_seq,state,harness_ref) VALUES(?,?,?,'running',COALESCE((SELECT content_ref FROM selected_strategy WHERE singleton=1),''))", id, owner, boundary.Int64); err != nil {
			return err
		}
		if _, err = db.ExecContext(ctx, "INSERT INTO round_inputs SELECT ?,seq FROM pending WHERE seq<=?", id, boundary.Int64); err != nil {
			return err
		}
		r, err = scanRound(db.QueryRowContext(ctx, "SELECT * FROM rounds WHERE id=?", id))
		return err
	})
	return r, err
}
func (c *Control) PrepareEffect(roundID, key, kind string, request Object) (Effect, error) {
	var e Effect
	if key == "" || kind == "" || request == nil {
		return e, errors.New("effect key, kind and request required")
	}
	fingerprint, err := Digest(Object{"kind": kind, "request": request})
	if err != nil {
		return e, err
	}
	body, err := Canonical(request)
	if err != nil {
		return e, err
	}
	err = Immediate(c.Path, func(db *sql.Conn) error {
		ctx := context.Background()
		if err := c.Guard(db, roundID); err != nil {
			return err
		}
		old, err := scanEffect(db.QueryRowContext(ctx, "SELECT * FROM effects WHERE round_id=? AND key=?", roundID, key))
		if err == nil {
			if old.Digest != fingerprint {
				return fmt.Errorf("%w: effect identity reused with different request", ErrConflict)
			}
			if old.Status != "completed" {
				return ErrUnknownEffect
			}
			e = old
			return nil
		}
		if !errors.Is(err, sql.ErrNoRows) {
			return err
		}
		var state string
		if err = db.QueryRowContext(ctx, "SELECT state FROM rounds WHERE id=?", roundID).Scan(&state); err != nil || state != "running" {
			return fmt.Errorf("%w: Round not running", ErrConflict)
		}
		id, err := ID()
		if err != nil {
			return err
		}
		if _, err = db.ExecContext(ctx, "INSERT INTO effects(id,round_id,key,kind,request,digest,status) VALUES(?,?,?,?,?,?,'intent')", id, roundID, key, kind, body, fingerprint); err != nil {
			return err
		}
		if kind == "tool.exec" {
			if _, err = db.ExecContext(ctx, "UPDATE effects SET content_delivery='pending' WHERE id=?", id); err != nil {
				return err
			}
		}
		e, err = scanEffect(db.QueryRowContext(ctx, "SELECT * FROM effects WHERE id=?", id))
		return err
	})
	return e, err
}
func (c *Control) CheckpointEffect(id string, receipt Object) error {
	return c.objectUpdate("UPDATE effects SET receipt=? WHERE id=? AND status!='completed'", id, receipt)
}
func (c *Control) CompleteEffect(id string, result Object) error {
	return c.objectUpdate("UPDATE effects SET status='completed',resolution='native_result',content_delivery=CASE WHEN content_delivery='not_required' THEN 'not_required' ELSE 'confirmed' END,result=? WHERE id=? AND status!='completed' AND dispatch_state='attempted'", id, result)
}
func (c *Control) objectUpdate(query, id string, value Object) error {
	if value == nil {
		return errors.New("object required")
	}
	body, err := Canonical(value)
	if err != nil {
		return err
	}
	return Immediate(c.Path, func(db *sql.Conn) error {
		if err := requireOne(db.ExecContext(context.Background(), query, body, id)); err != nil {
			return err
		}
		_, err := db.ExecContext(context.Background(), "INSERT INTO effect_observations(effect_id,kind,body) VALUES(?,?,?)", id, "adapter_observation", body)
		return err
	})
}

// AttemptEffect is the only dispatch permit. It is durably consumed before any
// remote call; even a crash immediately afterwards cannot turn it into prepared.
func (c *Control) AttemptEffect(id, owner string) error {
	if owner == "" {
		return errors.New("dispatch owner required")
	}
	return Immediate(c.Path, func(db *sql.Conn) error {
		if err := c.Guard(db, c.RoundID); err != nil {
			return err
		}
		return requireOne(db.ExecContext(context.Background(), `UPDATE effects SET dispatch_state='attempted',observation='running' WHERE id=? AND dispatch_state='prepared' AND resolution='unresolved' AND EXISTS(SELECT 1 FROM rounds WHERE rounds.id=effects.round_id AND owner=? AND state='running')`, id, owner))
	})
}
func (c *Control) UnknownEffect(id, message string) error {
	return Immediate(c.Path, func(db *sql.Conn) error {
		return requireOne(db.ExecContext(context.Background(), "UPDATE effects SET status='unknown',observation='unknown',error=? WHERE id=? AND status!='completed'", message, id))
	})
}
func unresolved(db *sql.Conn, roundID string) (bool, error) {
	var n int
	err := db.QueryRowContext(context.Background(), "SELECT count(*) FROM effects WHERE round_id=? AND (resolution='unresolved' OR content_delivery IN('pending','unknown','failed'))", roundID).Scan(&n)
	return n > 0, err
}
func (c *Control) FinishRound(id, revision string) error {
	return Immediate(c.Path, func(db *sql.Conn) error {
		ctx := context.Background()
		if err := c.Guard(db, id); err != nil {
			return err
		}
		r, err := scanRound(db.QueryRowContext(ctx, "SELECT * FROM rounds WHERE id=? AND state='running'", id))
		if err != nil {
			return fmt.Errorf("%w: Round not running", ErrConflict)
		}
		pending, err := unresolved(db, id)
		if err != nil {
			return err
		}
		if pending {
			return ErrUnknownEffect
		}
		if _, err = c.saveCheckpoint(db, r, Object{"content_ref": revision}, "handed_off"); err != nil {
			return err
		}
		if err = requireOne(db.ExecContext(ctx, "UPDATE rounds SET state='handed_off',revision=? WHERE id=?", revision, id)); err != nil {
			return err
		}
		_, err = db.ExecContext(ctx, "DELETE FROM pending WHERE seq IN(SELECT seq FROM round_inputs WHERE round_id=?)", r.ID)
		return err
	})
}
func (c *Control) PauseRound(id, message string, checkpoint Object) error {
	return Immediate(c.Path, func(db *sql.Conn) error {
		if err := c.Guard(db, id); err != nil {
			return err
		}
		round, err := scanRound(db.QueryRowContext(context.Background(), "SELECT * FROM rounds WHERE id=? AND state='running'", id))
		if err != nil {
			return err
		}
		var value any
		if checkpoint != nil {
			unknown, err := unresolved(db, id)
			if err != nil {
				return err
			}
			if unknown {
				return ErrUnknownEffect
			}
			ref, err := c.saveCheckpoint(db, round, checkpoint, "continuation")
			if err != nil {
				return err
			}
			raw, err := (Records{Directory: filepath.Join(filepath.Dir(c.Path), "records")}).Get(ref)
			if err != nil {
				return err
			}
			value = string(raw)
		}
		return requireOne(db.ExecContext(context.Background(), "UPDATE rounds SET state=?,error=?,checkpoint=COALESCE(?,checkpoint) WHERE id=? AND state='running'", pauseState(checkpoint), message, value, id))
	})
}
func (c *Control) ResumeRound(owner string) (Round, error) {
	var r Round
	if owner == "" {
		return r, errors.New("owner required")
	}
	err := Immediate(c.Path, func(db *sql.Conn) error {
		ctx := context.Background()
		var err error
		r, err = scanRound(db.QueryRowContext(ctx, "SELECT * FROM rounds WHERE state IN('ready','running','recovering','blocked')"))
		if err != nil || r.State != "ready" {
			return fmt.Errorf("%w: no confirmed paused continuation; takeover forbidden", ErrConflict)
		}
		unknown, err := unresolved(db, r.ID)
		if err != nil {
			return err
		}
		if unknown {
			return ErrUnknownEffect
		}
		if err = requireOne(db.ExecContext(ctx, "UPDATE rounds SET state='running',owner=?,epoch=epoch+1,error=NULL WHERE id=? AND state='ready'", owner, r.ID)); err != nil {
			return err
		}
		r.Owner, r.State, r.Error = owner, "running", ""
		r.Epoch++
		return nil
	})
	return r, err
}
func (c *Control) RejectIfUndispatched(id string) (bool, error) {
	var rejected bool
	err := Immediate(c.Path, func(db *sql.Conn) error {
		ctx := context.Background()
		if err := c.Guard(db, id); err != nil {
			return err
		}
		var n int
		if err := db.QueryRowContext(ctx, "SELECT count(*) FROM effects WHERE round_id=?", id).Scan(&n); err != nil {
			return err
		}
		if n > 0 {
			return nil
		}
		res, err := db.ExecContext(ctx, "UPDATE rounds SET state='blocked',error='local failure before dispatch' WHERE id=? AND state='running'", id)
		if err != nil {
			return err
		}
		count, err := res.RowsAffected()
		rejected = count == 1
		return err
	})
	return rejected, err
}
func (c *Control) Rounds() ([]Round, error) {
	db, err := OpenDB(c.Path)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	rows, err := db.Query("SELECT * FROM rounds ORDER BY rowid")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := []Round{}
	for rows.Next() {
		r, err := scanRound(rows)
		if err != nil {
			return nil, err
		}
		result = append(result, r)
	}
	return result, rows.Err()
}
func (c *Control) Effects(roundID string) ([]Effect, error) {
	db, err := OpenDB(c.Path)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	rows, err := db.Query("SELECT * FROM effects WHERE round_id=? ORDER BY rowid", roundID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := []Effect{}
	for rows.Next() {
		e, err := scanEffect(rows)
		if err != nil {
			return nil, err
		}
		result = append(result, e)
	}
	return result, rows.Err()
}

func (c *Control) AllocationReleaseObserved(id string, confirmed bool) error {
	state := "unknown"
	if confirmed {
		state = "confirmed"
	}
	return Immediate(c.Path, func(db *sql.Conn) error {
		return requireOne(db.ExecContext(context.Background(), "UPDATE allocations SET release_state=CASE WHEN release_state='confirmed' THEN 'confirmed' ELSE ? END WHERE id=?", state, id))
	})
}

// saveCheckpoint runs under the Work transaction after all referenced file and
// native-input records are durable. It fixes exact inputs and every independent
// resource-copy predecessor; later shared-project changes are irrelevant.
func (c *Control) saveCheckpoint(db *sql.Conn, round Round, provided Object, phase string) (RecordRef, error) {
	var empty RecordRef
	data := Object{}
	for k, v := range round.Checkpoint {
		data[k] = v
	}
	for k, v := range provided {
		data[k] = v
	}
	id, err := ID()
	if err != nil {
		return empty, err
	}
	ctx := context.Background()
	var previous sql.NullString
	if err = db.QueryRowContext(ctx, "SELECT (SELECT id FROM checkpoints ORDER BY rowid DESC LIMIT 1)").Scan(&previous); err != nil {
		return empty, err
	}
	var watermark int64
	if err = db.QueryRowContext(ctx, "SELECT COALESCE(MAX(seq),0) FROM events").Scan(&watermark); err != nil {
		return empty, err
	}
	rows, err := db.QueryContext(ctx, "SELECT seq FROM round_inputs WHERE round_id=? ORDER BY seq", round.ID)
	if err != nil {
		return empty, err
	}
	claimed := []string{}
	for rows.Next() {
		var seq int64
		if err = rows.Scan(&seq); err != nil {
			rows.Close()
			return empty, err
		}
		claimed = append(claimed, fmt.Sprintf("F%d", seq))
	}
	if err = errors.Join(rows.Err(), rows.Close()); err != nil {
		return empty, err
	}
	rows, err = db.QueryContext(ctx, "SELECT id,alias,target,generation,content_ref FROM resource_copies ORDER BY id")
	if err != nil {
		return empty, err
	}
	copies := []Object{}
	for rows.Next() {
		var id, alias, target, ref string
		var generation int64
		if err = rows.Scan(&id, &alias, &target, &generation, &ref); err != nil {
			rows.Close()
			return empty, err
		}
		value, e := DecodeObject(ref)
		if e != nil {
			rows.Close()
			return empty, e
		}
		copies = append(copies, Object{"working_copy_id": id, "alias": alias, "target": target, "generation": strconv.FormatInt(generation, 10), "content_ref": value})
	}
	if err = errors.Join(rows.Err(), rows.Close()); err != nil {
		return empty, err
	}
	rows, err = db.QueryContext(ctx, "SELECT * FROM effects WHERE round_id=? ORDER BY rowid", round.ID)
	if err != nil {
		return empty, err
	}
	effects := []Effect{}
	for rows.Next() {
		e, x := scanEffect(rows)
		if x != nil {
			rows.Close()
			return empty, x
		}
		effects = append(effects, e)
	}
	if err = errors.Join(rows.Err(), rows.Close()); err != nil {
		return empty, err
	}
	data["effects"] = effects
	data["schema_version"], data["checkpoint_id"], data["previous_checkpoint_id"] = 1, id, previous.String
	data["round_id"], data["epoch"], data["harness_ref"], data["phase"] = round.ID, strconv.FormatInt(round.Epoch, 10), round.HarnessRef, phase
	data["claimed_input_ids"], data["fact_watermark"], data["resource_copies"] = claimed, strconv.FormatInt(watermark, 10), copies
	body, err := json.Marshal(data)
	if err != nil {
		return empty, err
	}
	ref, err := (Records{Directory: filepath.Join(filepath.Dir(c.Path), "records")}).Put(body, "application/vnd.loom.checkpoint+json")
	if err != nil {
		return empty, err
	}
	encoded, err := json.Marshal(ref)
	if err != nil {
		return empty, err
	}
	_, err = db.ExecContext(ctx, "INSERT INTO checkpoints(id,round_id,owner,record_ref) VALUES(?,?,?,?)", id, round.ID, round.Owner, string(encoded))
	return ref, err
}

func pauseState(checkpoint Object) string {
	if checkpoint == nil {
		return "blocked"
	}
	return "ready"
}

// NativeEffect records only the adapter's terminal observation. Capturing files,
// model delivery and resource release are separate responsibilities.
func (c *Control) NativeEffect(id string, result Object) error {
	return c.objectUpdate("UPDATE effects SET resolution='native_result',result=? WHERE id=? AND status!='completed' AND dispatch_state='attempted'", id, result)
}

func (c *Control) EffectByKey(roundID, key string) (*Effect, error) {
	db, err := OpenDB(c.Path)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	e, err := scanEffect(db.QueryRow("SELECT * FROM effects WHERE round_id=? AND key=?", roundID, key))
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &e, nil
}
