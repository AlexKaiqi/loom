// Package rpc runs an independently deployed JSON-RPC program. Framing and
// dispatch are supplied by Sourcegraph; this package owns process lifetime only.
package rpc

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/sourcegraph/jsonrpc2"
	"golang.org/x/sys/unix"
)

type Handler func(context.Context, string, json.RawMessage) (any, error)

var ErrTransport = errors.New("worker transport failed; outcome may be unknown")

type pipe struct {
	io.Reader
	io.WriteCloser
	reader io.Closer
}

func (p *pipe) Close() error { _ = p.reader.Close(); return p.WriteCloser.Close() }

type quietLogger struct{}

func (quietLogger) Printf(string, ...interface{}) {}

type Client struct {
	conn      *jsonrpc2.Conn
	cmd       *exec.Cmd
	cancel    context.CancelFunc
	exited    chan struct{}
	once      sync.Once
	stopOnce  sync.Once
	mu        sync.Mutex
	closing   bool
	callbacks sync.WaitGroup
	counter   atomic.Uint64
	ready     atomic.Bool
	session   Session
}

type receiver struct {
	client *Client
	fn     Handler
}

func (h receiver) Handle(ctx context.Context, conn *jsonrpc2.Conn, req *jsonrpc2.Request) {
	h.client.mu.Lock()
	if h.client.closing {
		h.client.mu.Unlock()
		return
	}
	h.client.callbacks.Add(1)
	h.client.mu.Unlock()
	defer h.client.callbacks.Done()
	if req.Notif {
		return
	}
	var params json.RawMessage
	if req.Params != nil {
		params = *req.Params
	}
	var value any
	var err error
	if !h.client.ready.Load() {
		err = &Error{Kind: "not_ready"}
	} else if denied := h.client.session.authorize(req.Method, params); denied != nil {
		err = denied
	} else if h.fn == nil {
		err = errors.New("unsupported callback")
	} else {
		value, err = h.fn(ctx, req.Method, params)
	}
	if req.Notif {
		return
	}
	// Error details may contain a provider request or credentials. Never echo them.
	if err != nil {
		_ = conn.ReplyWithError(ctx, req.ID, &jsonrpc2.Error{Code: -32001, Message: "host callback failed; inspect durable state", Data: errorData(publicKind(err))})
	} else {
		_ = conn.Reply(ctx, req.ID, value)
	}
}

func Start(parent context.Context, command []string, directory string, handler Handler, role string, sessions ...Session) (*Client, error) {
	if len(command) == 0 || command[0] == "" {
		return nil, errors.New("worker command is required")
	}
	var session Session
	if len(sessions) > 1 {
		return nil, errors.New("one bound session required")
	}
	if len(sessions) == 1 {
		session = sessions[0]
	}
	ctx, cancel := context.WithCancel(parent)
	cmd := exec.Command(command[0], command[1:]...)
	cmd.Dir = directory
	cmd.Env = []string{}
	for _, key := range []string{"PATH", "LANG", "LC_ALL", "TMPDIR"} {
		if val, ok := os.LookupEnv(key); ok {
			cmd.Env = append(cmd.Env, key+"="+val)
		}
	}
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	cmd.Stderr = io.Discard
	if session.LogDirectory != "" {
		for _, name := range []string{"stdout", "stderr"} {
			f, e := os.OpenFile(filepath.Join(session.LogDirectory, name+".log"), os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
			if e != nil {
				cancel()
				return nil, e
			}
			defer f.Close()
			if name == "stdout" {
				cmd.Stdout = f
			} else {
				cmd.Stderr = f
			}
		}
	}
	// macOS has no SOCK_CLOEXEC flag. Hold Go's fork lock while installing it
	// explicitly so a concurrent worker cannot inherit another control channel.
	syscall.ForkLock.RLock()
	pair, err := unix.Socketpair(unix.AF_UNIX, unix.SOCK_STREAM, 0)
	if err == nil {
		syscall.CloseOnExec(pair[0])
		syscall.CloseOnExec(pair[1])
	}
	syscall.ForkLock.RUnlock()
	if err != nil {
		cancel()
		return nil, err
	}
	parentChannel := os.NewFile(uintptr(pair[0]), "loom-control")
	childChannel := os.NewFile(uintptr(pair[1]), "loom-control-child")
	cmd.ExtraFiles = []*os.File{childChannel}
	cmd.Stdin = nil
	if cmd.Stdout == nil {
		cmd.Stdout = io.Discard
	}
	if err = ctx.Err(); err == nil {
		err = cmd.Start()
	}
	_ = childChannel.Close()
	if err != nil {
		parentChannel.Close()
		cancel()
		return nil, errors.New("could not start configured worker")
	}
	c := &Client{cmd: cmd, cancel: cancel, exited: make(chan struct{}), session: session}
	codec := &JSONLines{}
	codec.Limit.Store(HandshakeLimit)
	c.conn = jsonrpc2.NewConn(ctx, jsonrpc2.NewBufferedStream(parentChannel, codec), jsonrpc2.AsyncHandler(receiver{c, handler}), jsonrpc2.SetLogger(quietLogger{}))
	go func() { _ = cmd.Wait(); close(c.exited) }()
	helloCtx, helloCancel := context.WithTimeout(ctx, 5*time.Second)
	defer helloCancel()
	var response struct {
		Version      string   `json:"protocol_version"`
		Role         string   `json:"role"`
		MaxFrame     int64    `json:"max_frame_bytes"`
		Capabilities []string `json:"capabilities"`
	}
	required := append([]string{role + "/1"}, session.RequiredCapabilities...)
	err = c.Call(helloCtx, "session.hello", map[string]any{"protocol_version": "loom/1", "schema_version": 1, "role": "runtime", "peer_role": role, "max_frame_bytes": FrameLimit, "capabilities": session.Capabilities, "required_capabilities": required, "session": session}, &response)
	if err != nil || response.Version != "loom/1" || response.Role != role || response.MaxFrame < HandshakeLimit || response.MaxFrame > FrameLimit {
		c.Close()
		return nil, errors.New("worker protocol handshake failed")
	}
	for _, needed := range required {
		supported := false
		for _, capability := range response.Capabilities {
			if capability == needed {
				supported = true
			}
		}
		if !supported {
			c.Close()
			return nil, errors.New("worker missing required capability: " + needed)
		}
	}
	c.ready.Store(true)
	codec.Limit.Store(response.MaxFrame)
	return c, nil
}

func (c *Client) Call(ctx context.Context, method string, params any, result any) error {
	id := jsonrpc2.ID{Num: c.counter.Add(1)}
	var raw json.RawMessage
	done := make(chan error, 1)
	// The upstream library's stream write does not observe ctx. Keep ownership
	// here so a child which never reads stdin cannot defeat a request deadline.
	go func() { done <- c.conn.Call(ctx, method, params, &raw, jsonrpc2.PickID(id)) }()
	var err error
	select {
	case err = <-done:
	case <-ctx.Done():
		err = ctx.Err()
	}
	if ctx.Err() != nil {
		notified := make(chan struct{})
		go func() {
			_ = c.conn.Notify(context.Background(), "$/cancelRequest", map[string]any{"id": id})
			close(notified)
		}()
		select {
		case <-notified:
		case <-time.After(50 * time.Millisecond):
		}
		// Do not join callbacks here: Call is also valid inside a callback. The
		// outer process owner joins them in Close after the callback can return.
		c.stop()
		<-notified
		return ErrTransport
	}
	if err != nil {
		return ErrTransport
	}
	if result == nil {
		return nil
	}
	if err = Decode(raw, result); err != nil {
		return errors.New("worker returned invalid JSON result")
	}
	return nil
}

func Decode(data []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return errors.New("trailing JSON data")
	}
	return nil
}

func (c *Client) stop() {
	c.stopOnce.Do(func() {
		c.mu.Lock()
		c.closing = true
		c.mu.Unlock()
		c.cancel()
		_ = c.conn.Close()
		_ = syscall.Kill(-c.cmd.Process.Pid, syscall.SIGTERM)
	})
}
func (c *Client) Close() {
	c.once.Do(func() {
		c.stop()
		select {
		case <-c.exited:
		case <-time.After(500 * time.Millisecond):
		}
		// A worker may leave descendants even after its own exit.
		_ = syscall.Kill(-c.cmd.Process.Pid, syscall.SIGKILL)
		<-c.exited
		c.callbacks.Wait()
	})
}

func Command(command []string, directory string) ([]string, error) {
	out := make([]string, len(command))
	for i, item := range command {
		if strings.Contains(item, "{python}") {
			return nil, errors.New("policy executable must be explicit; interpreter placeholders are unsupported")
		}
		out[i] = strings.ReplaceAll(item, "{harness}", directory)
	}
	return out, nil
}

func errorData(kind string) *json.RawMessage {
	body, _ := json.Marshal(map[string]string{"kind": kind})
	raw := json.RawMessage(body)
	return &raw
}
