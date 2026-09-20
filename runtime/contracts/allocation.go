package contracts

import "context"

// AllocationProvider is the small resource lifecycle core, independent of Bash
// execution. An allocated resource is not yet a verified tool execution domain.
type AllocationProvider interface {
	Binding() Binding
	Acquire(context.Context, string, string) (AllocationResult, error)
	InspectAllocation(context.Context, string, string) (AllocationResult, error)
	Release(context.Context, string) error
}
type AllocationResult struct {
	ID     string         `json:"sandbox_id,omitempty"`
	State  string         `json:"state"`
	Native map[string]any `json:"native"`
}
