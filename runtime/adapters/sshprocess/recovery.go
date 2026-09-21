package sshprocess

import (
	"context"
	"errors"
	"loom/runtime/contracts"
	"strings"
)

func emptyGroupCommand(unit string) string {
	events := "/sys/fs/cgroup/system.slice/" + unit + "/cgroup.events"
	return "if test -e " + quote(events) + "; then grep -qx 'populated 0' " + quote(events) + "; fi"
}

func (c *Client) reference(id, execution string, expected contracts.Binding) (string, error) {
	if expected != c.binding {
		return "", errors.New("original provider binding required")
	}
	p, e := c.allocationPath(id)
	if e != nil {
		return "", e
	}
	prefix := "loom-" + strings.TrimPrefix(id, "alloc-") + "-"
	op := strings.TrimSuffix(strings.TrimPrefix(execution, prefix), ".service")
	if !digestPattern.MatchString(op) || execution != unitName(id, op) {
		return "", errors.New("execution does not belong to original allocation")
	}
	return p + "/" + op, nil
}
func (c *Client) Query(ctx context.Context, id, execution string, expected contracts.Binding) (result map[string]any, err error) {
	p, e := c.reference(id, execution, expected)
	if e != nil {
		return nil, e
	}
	err = c.withConnection(ctx, func(x *connection) error {
		s, e := nativeStatus(x, execution)
		if e != nil {
			return e
		}
		out, e := x.read(p+"/stdout", 256<<20)
		if e != nil {
			return e
		}
		errout, e := x.read(p+"/stderr", 256<<20)
		if e != nil {
			return e
		}
		result = map[string]any{"status": s, "stdout": string(out), "stderr": string(errout), "business_outcome": "unknown", "execution_id": execution}
		return nil
	})
	return
}
func (c *Client) Cancel(ctx context.Context, id, execution string, expected contracts.Binding) (result map[string]any, err error) {
	if _, e := c.reference(id, execution, expected); e != nil {
		return nil, e
	}
	err = c.withConnection(ctx, func(x *connection) error {
		s, e := nativeStatus(x, execution)
		if e != nil {
			return e
		}
		if _, e = x.run("systemctl stop " + quote(execution)); e != nil {
			return e
		}
		// Stop waits for systemd's control-group cleanup; check the original
		// cgroup directly, including when the transient unit is unloaded.
		if _, e = x.run(emptyGroupCommand(execution)); e != nil {
			return e
		}
		result = map[string]any{"cancelled": true, "execution_fenced": true, "execution_id": execution, "status_before_cancel": s, "business_outcome": "unknown"}
		return nil
	})
	return
}
