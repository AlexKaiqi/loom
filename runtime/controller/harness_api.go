package controller

import (
	"context"
	"database/sql"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"loom/runtime/authority"
	"loom/runtime/rpc"
	"loom/runtime/store"
)

var harnessOperations = operationNames()

type boundFactView struct {
	store.FactView
	MountPath string
}
type projectionBasis struct {
	ContentRef, ViewID, Watermark string
	Resources                     Object
}
type harnessAPIState struct {
	callMu      sync.Mutex
	handoff     Object
	advancePlan Object
	advanceKey  string
	advanceRef  store.RecordRef
	advanceMu   sync.Mutex
	basis       projectionBasis
	published   map[string]store.RecordRef
	publishMu   sync.Mutex
	mu          sync.Mutex
	records     map[string]store.RecordRef
	views       map[string]boundFactView
}

func (c *run) allowRecord(ref store.RecordRef) {
	c.api.mu.Lock()
	defer c.api.mu.Unlock()
	if c.api.records == nil {
		c.api.records = map[string]store.RecordRef{}
	}
	c.api.records[ref.SHA256] = ref
}
func (c *run) readPolicyRecord(ref store.RecordRef) ([]byte, error) {
	c.api.mu.Lock()
	saved, ok := c.api.records[ref.SHA256]
	c.api.mu.Unlock()
	if !ok || saved != ref {
		return nil, &rpc.Error{Kind: "permission_denied"}
	}
	return (store.Records{Directory: c.work.ArtifactsDir()}).Get(ref)
}
func (c *run) harnessCall(ctx context.Context, method string, raw json.RawMessage) (result any, err error) {
	defer func() { err = harnessError(method, err) }()
	c.api.callMu.Lock()
	defer c.api.callMu.Unlock()
	if err := c.work.Control.Owned(func() error { return nil }); err != nil {
		return nil, &rpc.Error{Kind: "stale_epoch"}
	}
	var params harnessParams
	if err := decodeHarnessParams(method, raw, &params); err != nil {
		return nil, &rpc.Error{Kind: "invalid_request"}
	}
	if params.Protocol != "loom/1" || params.Schema != 1 {
		return nil, &rpc.Error{Kind: "unsupported_version"}
	}
	c.api.mu.Lock()
	handedOff := c.api.handoff != nil
	c.api.mu.Unlock()
	if handedOff {
		return nil, &rpc.Error{Kind: "not_ready", Diagnostic: "handoff already accepted"}
	}
	switch method {
	case "allocation.acquire":
		return c.acquireAllocation(ctx, params.RequestKey, params.Target)
	case "allocation.inspect":
		return c.runtime.Allocation(ctx, c.work, c.round.ID, params.ID, "inspect")
	case "allocation.release":
		return c.runtime.Allocation(ctx, c.work, c.round.ID, params.ID, "release")
	case "effect.request":
		return c.requestTool(ctx, params.RequestKey, params.Kind, params.Environment, params.Target, params.PayloadRef)
	case "checkpoint.commit":
		c.mu.Lock()
		defer c.mu.Unlock()
		version, err := c.work.CurrentContent()
		if err != nil {
			return nil, err
		}
		if version != params.ContentVersion || params.ResourceCopies == nil {
			return nil, &rpc.Error{Kind: "baseline_conflict"}
		}
		cp, err := c.work.Control.CommitCandidate(c.round.ID, params.PreviousCheckpointID, version, params.ResourceCopies)
		if err != nil {
			return nil, err
		}
		return Object{"checkpoint_id": cp["checkpoint_id"], "content_version": version}, nil
	case "round.handoff":
		c.mu.Lock()
		defer c.mu.Unlock()
		if params.HandledInputs == nil {
			return nil, &rpc.Error{Kind: "invalid_request"}
		}
		cp, err := c.work.Control.RequestHandoff(c.round.ID, params.CheckpointID, params.HandledInputs, params.Intent)
		if err != nil {
			return nil, err
		}
		c.api.mu.Lock()
		c.api.handoff = cp
		c.api.mu.Unlock()
		return Object{"accepted": true, "checkpoint_id": cp["checkpoint_id"], "execution_fencing": "pending"}, nil
	case "model.start", "model.resume":
		c.api.advanceMu.Lock()
		defer c.api.advanceMu.Unlock()
		if params.RequestKey == "" {
			return nil, &rpc.Error{Kind: "invalid_request"}
		}
		var plan Object
		ref := params.ProjectionRef
		if method == "model.resume" {
			if c.round.Checkpoint == nil || params.CheckpointID != c.round.Checkpoint["checkpoint_id"] {
				return nil, &rpc.Error{Kind: "baseline_conflict"}
			}
			plan = object(c.round.Checkpoint["plan"])
			data, e := json.Marshal(c.round.Checkpoint["projection_ref"])
			if e != nil {
				return nil, e
			}
			if e = json.Unmarshal(data, &ref); e != nil {
				return nil, e
			}
		} else {
			c.api.mu.Lock()
			published, ok := c.api.published[ref.SHA256]
			c.api.mu.Unlock()
			if !ok || published != ref {
				return nil, &rpc.Error{Kind: "permission_denied"}
			}
			body, e := c.readPolicyRecord(ref)
			if e != nil {
				return nil, e
			}
			plan, e = store.DecodeObject(string(body))
			if e != nil {
				return nil, e
			}
		}
		if plan == nil || object(plan["context"]) == nil {
			return nil, &rpc.Error{Kind: "invalid_request"}
		}
		if c.api.advanceKey != "" {
			if c.api.advanceKey != params.RequestKey || c.api.advanceRef != ref {
				return nil, &rpc.Error{Kind: "identity_conflict"}
			}
			return Object{"accepted": true, "projection_ref": ref, "request_key": params.RequestKey}, nil
		}
		if err := c.validateSavedViews(plan); err != nil {
			return nil, err
		}
		if method == "model.start" {
			if plan["execution_mode"] == "context_repair" {
				return nil, &rpc.Error{Kind: "not_ready"}
			}
			if c.round.Checkpoint != nil {
				return nil, &rpc.Error{Kind: "not_ready"}
			}
			if err := c.work.Control.SaveModelAdvance(c.round.ID, Object{"plan": plan, "projection_ref": ref, "content_ref": plan["content_version"], "advance_request_key": params.RequestKey}); err != nil {
				return nil, err
			}
		}
		c.api.advancePlan, c.api.advanceKey, c.api.advanceRef = plan, params.RequestKey, ref
		return Object{"accepted": true, "projection_ref": ref, "request_key": params.RequestKey}, nil
	case "projection.publish":
		c.api.mu.Lock()
		basis := c.api.basis
		c.api.mu.Unlock()
		if params.ContentVersion != basis.ContentRef || params.ViewID != basis.ViewID || params.HarnessRef != c.round.HarnessRef {
			return nil, &rpc.Error{Kind: "baseline_conflict"}
		}
		raw, err := c.readPolicyRecord(params.Ref)
		if err != nil {
			return nil, err
		}
		candidate, err := store.DecodeObject(string(raw))
		if err != nil || object(candidate["context"]) == nil {
			return nil, &rpc.Error{Kind: "invalid_request"}
		}
		candidate["content_version"], candidate["harness_ref"] = basis.ContentRef, c.round.HarnessRef
		candidate["view_id"], candidate["fact_watermark"], candidate["resource_views"] = basis.ViewID, basis.Watermark, basis.Resources
		if err = c.validateSources(candidate, basis); err != nil {
			return nil, err
		}
		data, err := json.Marshal(candidate)
		if err != nil {
			return nil, err
		}
		ref, err := (store.Records{Directory: c.work.ArtifactsDir()}).Put(data, "application/vnd.loom.projection+json")
		if err != nil {
			return nil, err
		}
		if _, err = c.work.Events.AppendOwned("runtime", "projection:"+c.round.ID+":"+ref.SHA256, "projection.published", Object{"projection_ref": ref, "content_version": basis.ContentRef, "harness_ref": c.round.HarnessRef}); err != nil {
			return nil, err
		}
		c.allowRecord(ref)
		c.api.mu.Lock()
		if c.api.published == nil {
			c.api.published = map[string]store.RecordRef{}
		}
		c.api.published[ref.SHA256] = ref
		c.api.mu.Unlock()
		return Object{"projection_ref": ref}, nil
	case "record.put":
		c.api.publishMu.Lock()
		defer c.api.publishMu.Unlock()
		if params.MediaType == "" || (params.Path != "" && params.Data != "") {
			return nil, &rpc.Error{Kind: "invalid_request"}
		}
		var body []byte
		var err error
		if params.Path != "" {
			if filepath.IsAbs(params.Path) || filepath.Clean(params.Path) != params.Path || params.Path == "." || strings.HasPrefix(params.Path, "../") {
				return nil, &rpc.Error{Kind: "permission_denied"}
			}
			// The isolated writer is frozen before reading the candidate. Neither a
			// symlink race nor another Harness thread can swap bytes during publication.
			frozen, cancel := context.WithTimeout(ctx, 5*time.Second)
			defer cancel()
			if err = c.domain.scope.Freeze(frozen); err != nil {
				return nil, err
			}
			defer c.domain.scope.Thaw()
			root, e := os.OpenRoot(filepath.Join(c.domain.binding.Staging, "outputs"))
			if e != nil {
				return nil, e
			}
			defer root.Close()
			f, e := root.Open(params.Path)
			if e != nil {
				return nil, &rpc.Error{Kind: "dependency_missing"}
			}
			defer f.Close()
			info, e := f.Stat()
			if e != nil || !info.Mode().IsRegular() || info.Size() > 256<<20 {
				return nil, &rpc.Error{Kind: "invalid_request"}
			}
			body, err = io.ReadAll(io.LimitReader(f, (256<<20)+1))
			if len(body) > 256<<20 {
				return nil, &rpc.Error{Kind: "invalid_request"}
			}
		} else {
			if len(params.Data) > 2<<20 {
				return nil, &rpc.Error{Kind: "invalid_request"}
			}
			body, err = base64.StdEncoding.Strict().DecodeString(params.Data)
		}
		if err != nil {
			return nil, &rpc.Error{Kind: "invalid_request"}
		}
		ref, err := (store.Records{Directory: c.work.ArtifactsDir()}).Put(body, params.MediaType)
		if err != nil {
			return nil, err
		}
		c.allowRecord(ref)
		return ref, nil
	case "record.get":
		raw, err := c.readPolicyRecord(params.Ref)
		if err != nil {
			return nil, err
		}
		offset, err := strconv.ParseInt(params.Offset, 10, 64)
		if err != nil || offset < 0 || offset > int64(len(raw)) || params.Length < 1 || params.Length > 1<<20 {
			return nil, &rpc.Error{Kind: "invalid_request"}
		}
		end := min(offset+int64(params.Length), int64(len(raw)))
		return Object{"record_ref": params.Ref, "offset": params.Offset, "data_base64": base64.StdEncoding.EncodeToString(raw[offset:end]), "eof": end == int64(len(raw))}, nil
	case "view.open":
		if params.Scope == "checkpoint" {
			c.mu.Lock()
			defer c.mu.Unlock()
			return c.handoffBasis()
		}
		// Only views already fixed for this Round are accessible on this channel.
		c.api.mu.Lock()
		defer c.api.mu.Unlock()
		view, ok := c.api.views[params.ViewID]
		if !ok {
			return nil, &rpc.Error{Kind: "permission_denied"}
		}
		return Object{"schema_version": 1, "view_id": view.ID, "fact_watermark": view.Watermark, "database_path": view.MountPath + "/facts.sqlite"}, nil
	case "fact.read":
		c.api.mu.Lock()
		view, ok := c.api.views[params.ViewID]
		c.api.mu.Unlock()
		if !ok {
			return nil, &rpc.Error{Kind: "permission_denied"}
		}
		viewURL := url.URL{Scheme: "file", Path: filepath.Join(view.Directory, "facts.sqlite"), RawQuery: "mode=ro"}
		db, err := sql.Open("sqlite", viewURL.String())
		if err != nil {
			return nil, err
		}
		defer db.Close()
		var encoded string
		if err = db.QueryRow("SELECT record_ref FROM facts WHERE fact_id=?", params.FactID).Scan(&encoded); err != nil {
			return nil, &rpc.Error{Kind: "permission_denied"}
		}
		var ref store.RecordRef
		if err = json.Unmarshal([]byte(encoded), &ref); err != nil {
			return nil, err
		}
		c.allowRecord(ref)
		return Object{"fact_id": params.FactID, "record_ref": ref, "view_id": params.ViewID}, nil
	case "subscription.put":
		source, err := c.runtime.Authority.WorkByID(params.SourceWorkID)
		if err != nil {
			return nil, &rpc.Error{Kind: "permission_denied"}
		}
		if err = c.runtime.Authority.RelayAllowed(source, c.work); err != nil {
			return nil, &rpc.Error{Kind: "permission_denied"}
		}
		start, err := strconv.ParseInt(params.Start, 10, 64)
		if err != nil || start < 0 {
			return nil, &rpc.Error{Kind: "invalid_request"}
		}
		if err = c.work.Events.Subscribe(params.ID, params.SourceWorkID, params.Kinds, start); err != nil {
			return nil, err
		}
		return Object{"subscription_id": params.ID, "accepted": true}, nil
	case "subscription.remove":
		if err := c.work.Events.RemoveSubscription(params.ID); err != nil {
			return nil, err
		}
		return Object{"subscription_id": params.ID, "removed": true}, nil
	case "effect.inspect":
		effects, err := c.work.Control.Effects(c.round.ID)
		if err != nil {
			return nil, err
		}
		for _, e := range effects {
			if e.ID == params.ID {
				return e, nil
			}
		}
		return nil, &rpc.Error{Kind: "permission_denied"}
	case "effect.cancel":
		return c.runtime.CancelRemote(ctx, c.work, c.round.ID, params.ID)
	}
	return nil, &rpc.Error{Kind: "capability_missing"}
}

func harnessError(method string, err error) error {
	if err == nil {
		return nil
	}
	var typed *rpc.Error
	if errors.As(err, &typed) {
		return err
	}
	kind := "internal_error"
	switch {
	case errors.Is(err, store.ErrUnknownEffect):
		kind = "outcome_unknown"
	case errors.Is(err, authority.ErrPermission):
		kind = "permission_denied"
	case errors.Is(err, store.ErrConflict):
		kind = "baseline_conflict"
		if method == "effect.request" || method == "subscription.put" || method == "allocation.acquire" {
			kind = "identity_conflict"
		}
	default:
		prefix, _, _ := strings.Cut(err.Error(), ":")
		switch prefix {
		case "invalid_request", "unsupported_version", "permission_denied", "stale_epoch", "identity_conflict", "baseline_conflict", "not_ready", "capability_missing", "dependency_missing", "outcome_unknown":
			kind = prefix
		}
	}
	return &rpc.Error{Kind: kind}
}
