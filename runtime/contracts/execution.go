// Package contracts contains implementation types for the HTML design book.
package contracts

import (
	"context"
	"time"
)

// Binding is the complete non-secret execution destination saved in the Work.
// ServiceID names a host resolver; Endpoint pins the concrete origin used for
// this attempt, so old native IDs cannot drift to a different service.
type Binding struct {
	ServiceID             string  `json:"service_id"`
	Endpoint              string  `json:"endpoint"`
	Image                 string  `json:"image"`
	Profile               string  `json:"profile"`
	CPU                   string  `json:"cpu"`
	Memory                string  `json:"memory"`
	LeaseSeconds          float64 `json:"lease_seconds"`
	RequestTimeoutSeconds float64 `json:"request_timeout_seconds"`
}
type Request struct {
	SandboxID           string
	AllocationRequestID string
	OperationID         string
	Target              string
	Script              string
	Timeout             time.Duration
	Directory           string
	ReadOnlyPaths       []string
	ArtifactsDir        string
}
type Checkpoint struct {
	Binding      Binding        `json:"binding"`
	Phase        string         `json:"phase"`
	NativeResult map[string]any `json:"native_result,omitempty"`
	Artifacts    []Artifact     `json:"artifacts,omitempty"`
	SandboxID    string         `json:"sandbox_id,omitempty"`
	ExecutionID  string         `json:"execution_id,omitempty"`
	Readiness    *Readiness     `json:"readiness,omitempty"`
}

// Readiness describes a measured execution domain, never a provider-wide flag.
// Its allocation/session binding and retained probe bytes accompany the report.
type Readiness struct {
	Platform      string            `json:"platform"`
	Architecture  string            `json:"architecture"`
	Shell         string            `json:"shell"`
	Tools         map[string]string `json:"tools"`
	UID           int               `json:"uid"`
	GID           int               `json:"gid"`
	Capabilities  map[string]string `json:"process_capabilities"`
	NoNewPrivs    bool              `json:"no_new_privileges"`
	Network       string            `json:"network"`
	Workspace     string            `json:"workspace"`
	ReadOnlyPaths []string          `json:"readonly_paths"`
}
type Artifact struct {
	Path     string `json:"path"`
	MIMEType string `json:"mime_type"`
	Size     int64  `json:"size"`
	SHA256   string `json:"sha256"`
}
type Result struct {
	Binding     Binding        `json:"binding"`
	OperationID string         `json:"operation_id"`
	Target      string         `json:"target"`
	State       string         `json:"state"`
	SandboxID   string         `json:"sandbox_id,omitempty"`
	ExecutionID string         `json:"execution_id,omitempty"`
	ExitCode    *int           `json:"exit_code"`
	Stdout      string         `json:"stdout"`
	Stderr      string         `json:"stderr"`
	Artifacts   []Artifact     `json:"artifacts"`
	Released    bool           `json:"released"`
	Error       string         `json:"error,omitempty"`
	Native      map[string]any `json:"native"`
	Readiness   *Readiness     `json:"readiness,omitempty"`
}

// TaskExecutor is the Runtime-owned execution seam. Native SDK values remain
// behind the provider adapter. No local Shell fallback is permitted.
type TaskExecutor interface {
	Binding() Binding
	Execute(context.Context, Request, func(Checkpoint) error) (Result, error)
	Query(context.Context, string, string, Binding) (map[string]any, error)
	Cancel(context.Context, string, string, Binding) (map[string]any, error)
	Release(context.Context, string) error
}
