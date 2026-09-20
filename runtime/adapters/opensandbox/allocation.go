package opensandbox

import (
	"context"
	"encoding/json"
	"errors"
	upstream "github.com/alibaba/OpenSandbox/sdks/sandbox/go"
	"loom/runtime/contracts"
	"time"
)

func allocationResult(info *upstream.SandboxInfo) (contracts.AllocationResult, error) {
	raw, err := json.Marshal(info)
	if err != nil {
		return contracts.AllocationResult{}, err
	}
	var native map[string]any
	if err = json.Unmarshal(raw, &native); err != nil {
		return contracts.AllocationResult{}, err
	}
	if info.ID == "" {
		return contracts.AllocationResult{}, errors.New("empty native allocation identity")
	}
	return contracts.AllocationResult{ID: info.ID, State: "observed", Native: native}, nil
}
func (c *Client) Acquire(ctx context.Context, requestID, target string) (contracts.AllocationResult, error) {
	if requestID == "" || target == "" {
		return contracts.AllocationResult{}, errors.New("allocation request and target required")
	}
	ttl := int(c.config.Lease / time.Second)
	info, err := c.lifecycle().CreateSandbox(ctx, upstream.CreateSandboxRequest{
		Image: &upstream.ImageSpec{URI: c.config.Image}, Timeout: &ttl, ResourceLimits: upstream.ResourceLimits{"cpu": c.config.CPU, "memory": c.config.Memory},
		Entrypoint: []string{"sleep", "infinity"}, Env: map[string]string{}, Metadata: map[string]string{"loom.operation": requestID, "loom.target": target, "loom.profile": c.config.Profile},
		Extensions: map[string]string{"bootstrap.execd.isolation": "enable"},
	})
	if err != nil {
		return contracts.AllocationResult{}, err
	}
	return allocationResult(info)
}
func (c *Client) InspectAllocation(ctx context.Context, requestID, id string) (contracts.AllocationResult, error) {
	if requestID == "" {
		return contracts.AllocationResult{}, errors.New("original allocation request required")
	}
	if id != "" {
		info, err := c.lifecycle().GetSandbox(ctx, id)
		if err != nil {
			var native *upstream.APIError
			if errors.As(err, &native) && native.StatusCode == 404 {
				return contracts.AllocationResult{ID: id, State: "absent", Native: map[string]any{"http_status": 404}}, nil
			}
			return contracts.AllocationResult{}, err
		}
		if info.ID != id || info.Metadata["loom.operation"] != requestID {
			return contracts.AllocationResult{}, errors.New("native allocation identity does not match original request")
		}
		return allocationResult(info)
	}
	response, err := c.lifecycle().ListSandboxes(ctx, upstream.ListOptions{Metadata: map[string]string{"loom.operation": requestID}, Page: 1, PageSize: 2})
	if err != nil {
		return contracts.AllocationResult{}, err
	}
	raw, err := json.Marshal(response)
	if err != nil {
		return contracts.AllocationResult{}, err
	}
	var native map[string]any
	if err = json.Unmarshal(raw, &native); err != nil {
		return contracts.AllocationResult{}, err
	}
	// Metadata filtering is native evidence, never a permit to create again.
	if len(response.Items) != 1 || response.Pagination.HasNextPage || response.Pagination.TotalItems > 1 {
		return contracts.AllocationResult{State: "unknown", Native: native}, nil
	}
	info := response.Items[0]
	if info.Metadata["loom.operation"] != requestID {
		return contracts.AllocationResult{}, errors.New("native metadata filter did not preserve request scope")
	}
	return allocationResult(&info)
}
