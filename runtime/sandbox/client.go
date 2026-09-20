// Package sandbox hands authorized content to the official remote OpenSandbox
// service. It neither launches local task processes nor owns durable effects.
package sandbox

import (
	"context"

	"encoding/json"
	"errors"
	"fmt"
	"io"
	"loom/runtime/filesystem"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	upstream "github.com/alibaba/OpenSandbox/sdks/sandbox/go"
)

const NativeLogRetention int64 = 16 << 20

type Config struct {
	ServiceID      string
	Endpoint       string
	APIKey         string `json:"-"`
	Image          string
	Profile        string
	Lease          time.Duration
	RequestTimeout time.Duration
	CPU            string
	Memory         string
}

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
	OperationID  string
	Target       string
	Script       string
	Timeout      time.Duration
	Directory    string
	ArtifactsDir string
}
type Checkpoint struct {
	Binding     Binding `json:"binding"`
	Phase       string  `json:"phase"`
	SandboxID   string  `json:"sandbox_id,omitempty"`
	ExecutionID string  `json:"execution_id,omitempty"`
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
}
type Client struct{ config Config }

func New(config Config) (*Client, error) {
	if !regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.-]*$`).MatchString(config.ServiceID) {
		return nil, errors.New("sandbox service ID must name an explicitly configured service")
	}
	parsed, err := url.Parse(config.Endpoint)
	if err != nil || parsed == nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Host == "" || parsed.User != nil || (parsed.Path != "" && parsed.Path != "/") || parsed.RawQuery != "" || parsed.Fragment != "" {
		return nil, errors.New("sandbox endpoint must be an HTTP(S) origin")
	}
	if !regexp.MustCompile(`^[^\s]+@sha256:[a-f0-9]{64}$`).MatchString(config.Image) {
		return nil, errors.New("sandbox image must be pinned by sha256 digest")
	}
	if config.Profile == "" {
		config.Profile = "code"
	}
	if config.Profile != "code" {
		return nil, errors.New("unsupported sandbox profile")
	}
	if config.Lease == 0 {
		config.Lease = 600 * time.Second
	}
	if config.RequestTimeout == 0 {
		config.RequestTimeout = 30 * time.Second
	}
	if config.Lease < time.Second || config.Lease%time.Second != 0 || config.RequestTimeout <= 0 {
		return nil, errors.New("sandbox lease must be a positive whole number of seconds and timeout must be positive")
	}
	if config.CPU == "" {
		config.CPU = "1"
	}
	if config.Memory == "" {
		config.Memory = "512Mi"
	}
	// Avoid the SDK's implicit environment-key fallback: deployment authority must
	// be explicit and must never be confused with a task-provided environment.
	if config.APIKey == "" {
		return nil, errors.New("sandbox API key must be explicitly configured")
	}
	config.Endpoint = strings.TrimRight(config.Endpoint, "/")
	return &Client{config: config}, nil
}
func (c *Client) Binding() Binding {
	return Binding{ServiceID: c.config.ServiceID, Endpoint: c.config.Endpoint, Image: c.config.Image, Profile: c.config.Profile, CPU: c.config.CPU, Memory: c.config.Memory, LeaseSeconds: c.config.Lease.Seconds(), RequestTimeoutSeconds: c.config.RequestTimeout.Seconds()}
}
func (c *Client) checkDestination(expected Binding) error {
	actual := c.Binding()
	if expected.ServiceID == "" || expected.ServiceID != actual.ServiceID || expected.Endpoint != actual.Endpoint {
		return errors.New("remote operation binding does not match the configured sandbox service and endpoint")
	}
	return nil
}
func (c *Client) connection() upstream.ConnectionConfig {
	return upstream.ConnectionConfig{Domain: c.config.Endpoint, APIKey: c.config.APIKey, UseServerProxy: true, RequestTimeout: c.config.RequestTimeout, Retry: &upstream.RetryConfig{MaxRetries: 0}, DisableMetrics: true}
}
func (c *Client) lifecycle() *upstream.LifecycleClient {
	return upstream.NewLifecycleClient(c.config.Endpoint+"/v1", c.config.APIKey, upstream.WithTimeout(c.config.RequestTimeout), upstream.WithRetry(upstream.RetryConfig{MaxRetries: 0}))
}
func quote(s string) string { return "'" + strings.ReplaceAll(s, "'", "'\"'\"'") + "'" }
func (c *Client) redact(err error) string {
	return strings.ReplaceAll(err.Error(), c.config.APIKey, "<redacted>")
}

// Execute dispatches at most one user command. Before any network operation an
// error is a local rejection; afterwards every error is an unknown Result.
func (c *Client) Execute(ctx context.Context, req Request, checkpoint func(Checkpoint) error) (Result, error) {
	result := Result{Binding: c.Binding(), OperationID: req.OperationID, Target: req.Target, State: "unknown", Artifacts: []Artifact{}, Native: map[string]any{}}
	if req.Target != "surface" && req.Target != "userspace" {
		return result, errors.New("target must be surface or userspace")
	}
	if req.OperationID == "" || req.Timeout <= 0 || req.Timeout >= c.config.Lease {
		return result, errors.New("operation identity and timeout within lease are required")
	}
	directory, err := filepath.Abs(req.Directory)
	if err != nil {
		return result, err
	}
	identity, err := os.Lstat(directory)
	if err != nil {
		return result, err
	}
	if !identity.IsDir() {
		return result, errors.New("authorized directory must be a real directory")
	}
	artifacts, err := filepath.Abs(req.ArtifactsDir)
	if err != nil {
		return result, err
	}
	if filesystem.Inside(directory, artifacts) {
		return result, errors.New("artifacts must be outside task content")
	}
	if err = os.MkdirAll(artifacts, 0700); err != nil {
		return result, err
	}
	canonicalDirectory, err := filepath.EvalSymlinks(directory)
	if err != nil {
		return result, err
	}
	canonicalArtifacts, err := filepath.EvalSymlinks(artifacts)
	if err != nil {
		return result, err
	}
	if filesystem.Inside(canonicalDirectory, canonicalArtifacts) {
		return result, errors.New("artifacts must be outside task content, including symlink aliases")
	}
	// The artifact directory itself may be new. Persist its parent entries too,
	// not only the file and the immediate containing directory in save().
	for current := canonicalArtifacts; ; current = filepath.Dir(current) {
		if err = filesystem.SyncDir(current); err != nil {
			return result, err
		}
		if filepath.Dir(current) == current {
			break
		}
	}
	temp, err := os.CreateTemp("", "loom-input-")
	if err != nil {
		return result, err
	}
	defer os.Remove(temp.Name())
	if err = filesystem.Archive(directory, temp); err != nil {
		temp.Close()
		return result, err
	}
	if _, err = temp.Seek(0, io.SeekStart); err != nil {
		temp.Close()
		return result, err
	}
	input, err := save(filepath.Join(artifacts, "input.tar"), temp)
	err = errors.Join(err, temp.Close())
	if err != nil {
		return result, err
	}
	input.MIMEType = "application/x-tar"
	result.Artifacts = append(result.Artifacts, input)
	// Check the source again before transferring it, catching concurrent writes
	// while creating the input snapshot. No remote operation exists at this point.
	if err = filesystem.Unchanged(directory, identity, input.SHA256); err != nil {
		return result, err
	}
	if checkpoint != nil {
		if err = checkpoint(Checkpoint{Phase: "planned", Binding: result.Binding}); err != nil {
			return result, err
		}
	}
	err = c.execute(ctx, req, directory, artifacts, identity, input.SHA256, &result, checkpoint)
	if err != nil {
		result.Error = c.redact(err)
	}
	return result, nil
}
func (c *Client) execute(ctx context.Context, req Request, directory, artifacts string, identity os.FileInfo, inputDigest string, result *Result, checkpoint func(Checkpoint) error) error {
	ttl := int(c.config.Lease / time.Second)
	info, err := c.lifecycle().CreateSandbox(ctx, upstream.CreateSandboxRequest{
		Image: &upstream.ImageSpec{URI: c.config.Image}, Timeout: &ttl, ResourceLimits: upstream.ResourceLimits{"cpu": c.config.CPU, "memory": c.config.Memory},
		Entrypoint: []string{"sleep", "infinity"}, Env: map[string]string{}, Metadata: map[string]string{"loom.operation": req.OperationID, "loom.target": req.Target, "loom.profile": c.config.Profile},
		Extensions: map[string]string{"bootstrap.execd.isolation": "enable"},
	})
	if err != nil {
		return err
	}
	result.SandboxID = info.ID
	record := func(phase string) error {
		if checkpoint == nil {
			return nil
		}
		return checkpoint(Checkpoint{Phase: phase, Binding: result.Binding, SandboxID: result.SandboxID, ExecutionID: result.ExecutionID})
	}
	if err = record("created"); err != nil {
		return err
	}
	sb, err := upstream.ConnectSandbox(ctx, c.connection(), info.ID, upstream.ReadyOptions{Timeout: c.config.RequestTimeout})
	if err != nil {
		return err
	}
	defer sb.Close()
	input, err := os.Open(filepath.Join(artifacts, "input.tar"))
	if err != nil {
		return err
	}
	err = sb.UploadFile(ctx, input, upstream.UploadFileOptions{FileName: "input.tar", Metadata: upstream.FileMetadata{Path: "/tmp/loom-input.tar", Mode: 600}})
	err = errors.Join(err, input.Close())
	if err != nil {
		return err
	}
	remote := "/workspace/" + req.Target
	if err = command(ctx, sb, "mkdir -p "+remote+" && tar -xf /tmp/loom-input.tar -C "+remote+" && chown -R 65534:65534 "+remote+" && rm /tmp/loom-input.tar"); err != nil {
		return err
	}
	uid := uint32(65534)
	share := true
	session, err := sb.IsolationCreate(ctx, upstream.CreateIsolatedSessionRequest{Workspace: upstream.IsolatedWorkspaceSpec{Path: remote, Mode: "rw"}, Profile: "strict", ShareNet: &share, Uid: &uid, Gid: &uid, EnvPassthrough: &upstream.EnvPassthroughSpec{Mode: "allow", Keys: []string{}}, IdleTimeoutSeconds: ttl})
	if err != nil {
		return err
	}
	preflight, err := session.Run(ctx, upstream.IsolatedRunRequest{Code: "/usr/local/bin/python -I -c " + quote("import os,socket\nassert os.getuid()==65534\ntry:\n socket.socket()\nexcept PermissionError:\n pass\nelse:\n raise RuntimeError('network syscalls must be denied')\n"), TimeoutSeconds: 30}, nil)
	if err != nil {
		return err
	}
	if preflight.Error != nil || preflight.ExitCode == nil || *preflight.ExitCode != 0 {
		result.Native["preflight"] = preflight
		return errors.New("sandbox code profile failed isolation preflight")
	}
	result.ExecutionID = session.SessionID() + "/"
	if err = record("prepared"); err != nil {
		return err
	}
	run, err := session.RunBackground(ctx, "cd "+remote+" && env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp LANG=C.UTF-8 /bin/sh -c "+quote(req.Script))
	if err != nil {
		return err
	}
	result.ExecutionID = session.SessionID() + "/" + run.RunID
	result.Native["session"] = session.Info()
	result.Native["run"] = run
	if err = record("accepted"); err != nil {
		return err
	}
	deadline := time.Now().Add(req.Timeout)
	cursor := int64(0)
	var logs strings.Builder
	var status *upstream.IsolatedRunStatus
	read := func() error {
		text, next, err := session.GetRunLogs(ctx, run.RunID, cursor)
		if err != nil {
			return err
		}
		if next >= NativeLogRetention {
			return errors.New("upstream log retention boundary reached; complete output cannot be confirmed")
		}
		logs.WriteString(text)
		cursor = next
		return nil
	}
	for {
		if err = read(); err != nil {
			return err
		}
		status, err = session.GetRunStatus(ctx, run.RunID)
		if err != nil {
			return err
		}
		result.Native["status"] = status
		if !status.Running {
			if err = read(); err != nil {
				return err
			}
			break
		}
		if !time.Now().Before(deadline) {
			cancelErr := session.Delete(ctx)
			return errors.Join(errors.New("execution deadline exceeded; isolated session deletion requested; reconcile partial files"), cancelErr)
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(100 * time.Millisecond):
		}
	}
	result.ExitCode = status.ExitCode
	result.Stdout = logs.String()
	if status.ExitCode == nil || status.Error != "" {
		return errors.New("executor did not confirm an intact terminal command result")
	}
	if err = session.Delete(ctx); err != nil {
		return err
	}
	native, err := json.MarshalIndent(result.Native, "", "  ")
	if err != nil {
		return err
	}
	for _, item := range []struct{ name, data, mime string }{{"stdout.txt", result.Stdout, "text/plain"}, {"stderr.txt", result.Stderr, "text/plain"}, {"execution.json", string(native), "application/json"}} {
		a, err := save(filepath.Join(artifacts, item.name), strings.NewReader(item.data))
		if err != nil {
			return err
		}
		a.MIMEType = item.mime
		result.Artifacts = append(result.Artifacts, a)
	}
	if err = command(ctx, sb, "tar -cf /tmp/loom-output.tar -C "+remote+" ."); err != nil {
		return err
	}
	output, err := sb.DownloadFile(ctx, "/tmp/loom-output.tar", "")
	if err != nil {
		return err
	}
	a, err := save(filepath.Join(artifacts, "workspace.tar"), output)
	err = errors.Join(err, output.Close())
	if err != nil {
		return err
	}
	a.MIMEType = "application/x-tar"
	result.Artifacts = append(result.Artifacts, a)
	if err = c.Release(ctx, result.SandboxID); err != nil {
		return err
	}
	result.Released = true
	snapshot, err := os.Open(a.Path)
	if err != nil {
		return err
	}
	err = filesystem.Restore(snapshot, directory, identity, inputDigest)
	err = errors.Join(err, snapshot.Close())
	if err != nil {
		return err
	}
	result.State = "completed"
	return nil
}
func command(ctx context.Context, sb *upstream.Sandbox, script string) error {
	response, err := sb.RunCommandWithOpts(ctx, upstream.RunCommandRequest{Command: script, Timeout: 30000}, nil)
	if err != nil {
		return err
	}
	if response.Error != nil || response.ExitCode == nil || *response.ExitCode != 0 {
		return fmt.Errorf("remote workspace command failed: %+v", response)
	}
	return nil
}
func splitExecution(executionID string) (string, string, error) {
	session, run, ok := strings.Cut(executionID, "/")
	if !ok || session == "" || strings.Contains(run, "/") {
		return "", "", errors.New("invalid execution reference")
	}
	return session, run, nil
}
func (c *Client) Query(ctx context.Context, sandboxID, executionID string, expected Binding) (map[string]any, error) {
	if err := c.checkDestination(expected); err != nil {
		return nil, err
	}
	sessionID, runID, err := splitExecution(executionID)
	if err != nil {
		return nil, err
	}
	sb, err := upstream.ConnectSandbox(ctx, c.connection(), sandboxID)
	if err != nil {
		return nil, err
	}
	defer sb.Close()
	session, err := sb.IsolationAttach(ctx, sessionID)
	if err != nil {
		return nil, err
	}
	var value any
	if runID == "" {
		value, err = session.Get(ctx)
	} else {
		value, err = session.GetRunStatus(ctx, runID)
	}
	if err != nil {
		return nil, err
	}
	encoded, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	var result map[string]any
	err = json.Unmarshal(encoded, &result)
	return result, err
}
func (c *Client) Cancel(ctx context.Context, sandboxID, executionID string, expected Binding) (map[string]any, error) {
	if err := c.checkDestination(expected); err != nil {
		return nil, err
	}
	sessionID, _, err := splitExecution(executionID)
	if err != nil {
		return nil, err
	}
	sb, err := upstream.ConnectSandbox(ctx, c.connection(), sandboxID)
	if err != nil {
		return nil, err
	}
	defer sb.Close()
	session, err := sb.IsolationAttach(ctx, sessionID)
	if err != nil {
		return nil, err
	}
	if err = session.Delete(ctx); err != nil {
		return nil, err
	}
	return map[string]any{"state": "session_deleted", "session_id": sessionID}, nil
}
func (c *Client) Release(ctx context.Context, sandboxID string) error {
	if sandboxID == "" {
		return errors.New("sandbox identity required")
	}
	return c.lifecycle().DeleteSandbox(ctx, sandboxID)
}
