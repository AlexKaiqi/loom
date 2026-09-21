package sshprocess

import (
	"context"
	"encoding/json"
	"errors"
	"loom/runtime/contracts"
	"os"
	"path"
	"strings"
)

type allocation struct {
	RequestID string `json:"request_id"`
	Target    string `json:"target"`
}

func allocationID(request string) string { return "alloc-" + digest(request) }
func (c *Client) allocationPath(id string) (string, error) {
	if !strings.HasPrefix(id, "alloc-") || !digestPattern.MatchString(strings.TrimPrefix(id, "alloc-")) {
		return "", errors.New("invalid allocation identity")
	}
	return path.Join(c.options.StateDirectory, id), nil
}
func (c *Client) acquire(x *connection, request, target string) (contracts.AllocationResult, error) {
	id := allocationID(request)
	p, _ := c.allocationPath(id)
	// Exclusive mkdir is the remote idempotency boundary. An interrupted create
	// is inspected, never repeated or overwritten, including after release.
	if _, e := x.run("test -d " + quote(c.options.StateDirectory) + " && test \"$(realpath -- " + quote(c.options.StateDirectory) + ")\" = " + quote(c.options.StateDirectory) + " && test \"$(stat -c '%u:%a' " + quote(c.options.StateDirectory) + ")\" = 0:711 && mkdir -m 711 -- " + quote(p)); e != nil {
		return contracts.AllocationResult{}, e
	}
	b, _ := json.Marshal(allocation{request, target})
	if e := x.put(p+"/allocation.json", strings.NewReader(string(b)), 0600); e != nil {
		return contracts.AllocationResult{}, e
	}
	if _, e := x.run("sync -f " + quote(p)); e != nil {
		return contracts.AllocationResult{}, e
	}
	return contracts.AllocationResult{ID: id, State: "observed", Native: map[string]any{"request_id": request, "target": target}}, nil
}
func (c *Client) Acquire(ctx context.Context, request, target string) (result contracts.AllocationResult, err error) {
	if request == "" || !namePattern.MatchString(target) {
		return result, errors.New("original request and logical target required")
	}
	err = c.withConnection(ctx, func(x *connection) error { var e error; result, e = c.acquire(x, request, target); return e })
	return
}
func (c *Client) inspect(x *connection, request, id string) (contracts.AllocationResult, error) {
	if request == "" || (id != "" && id != allocationID(request)) {
		return contracts.AllocationResult{}, errors.New("allocation does not match original request")
	}
	id = allocationID(request)
	p, _ := c.allocationPath(id)
	if _, e := x.files.Stat(p); os.IsNotExist(e) {
		return contracts.AllocationResult{State: "absent", Native: map[string]any{"request_id": request}}, nil
	} else if e != nil {
		return contracts.AllocationResult{}, e
	}
	b, e := x.read(p+"/allocation.json", 65536)
	if e != nil {
		return contracts.AllocationResult{}, e
	}
	var a allocation
	if json.Unmarshal(b, &a) != nil || a.RequestID != request {
		return contracts.AllocationResult{}, errors.New("incomplete or mismatched native allocation; do not replay")
	}
	state := "observed"
	if _, e = x.files.Stat(p + "/released"); e == nil {
		state = "absent"
	} else if !os.IsNotExist(e) {
		return contracts.AllocationResult{}, e
	}
	return contracts.AllocationResult{ID: id, State: state, Native: map[string]any{"request_id": a.RequestID, "target": a.Target}}, nil
}
func (c *Client) InspectAllocation(ctx context.Context, request, id string) (result contracts.AllocationResult, err error) {
	err = c.withConnection(ctx, func(x *connection) error { var e error; result, e = c.inspect(x, request, id); return e })
	return
}

// Release preserves allocation/operation tombstones. The caller must have saved
// content; an undelivered execution cannot be erased through this API.
func (c *Client) release(x *connection, id string) error {
	p, e := c.allocationPath(id)
	if e != nil {
		return e
	}
	entries, e := x.files.ReadDir(p)
	if e != nil {
		return e
	}
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		if !digestPattern.MatchString(entry.Name()) {
			return errors.New("unexpected allocation contents")
		}
		op := p + "/" + entry.Name()
		if _, e = x.files.Stat(op + "/delivered"); e != nil {
			return errors.New("execution content not acknowledged; retain original allocation")
		}
		unit := unitName(id, entry.Name())
		if _, e = x.run("if test \"$(systemctl show " + quote(unit) + " --property=LoadState --value)\" != not-found; then systemctl stop " + quote(unit) + "; fi\n" + emptyGroupCommand(unit)); e != nil {
			return e
		}
		cleanup := "rm -rf --"
		for _, name := range []string{"task", "input.tar", "workspace.tar", "stdout", "stderr", "command", "probe", "entry", "gate"} {
			cleanup += " " + quote(op+"/"+name)
		}
		if _, e = x.run(cleanup); e != nil {
			return e
		}
	}
	if _, e = x.files.Stat(p + "/released"); os.IsNotExist(e) {
		e = x.put(p+"/released", strings.NewReader("released\n"), 0600)
	}
	return e
}
func (c *Client) Release(ctx context.Context, id string) error {
	return c.withConnection(ctx, func(x *connection) error { return c.release(x, id) })
}
