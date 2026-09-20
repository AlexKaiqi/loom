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
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/sourcegraph/jsonrpc2"
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
	var params json.RawMessage
	if req.Params != nil {
		params = *req.Params
	}
	var value any
	var err error
	if h.fn == nil {
		err = errors.New("unsupported callback")
	} else {
		value, err = h.fn(ctx, req.Method, params)
	}
	if req.Notif {
		return
	}
	// Error details may contain a provider request or credentials. Never echo them.
	if err != nil {
		_ = conn.ReplyWithError(ctx, req.ID, &jsonrpc2.Error{Code: -32001, Message: "host callback failed; inspect durable state"})
	} else {
		_ = conn.Reply(ctx, req.ID, value)
	}
}

func Start(parent context.Context, command []string, directory string, handler Handler) (*Client, error) {
	if len(command) == 0 || command[0] == "" {
		return nil, errors.New("worker command is required")
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
	// Own the pipe descriptors: exec.Wait must not close StdoutPipe before the
	// JSON-RPC reader drains a final response from a worker that exits promptly.
	childIn, in, err := os.Pipe()
	if err != nil {
		cancel()
		return nil, ErrTransport
	}
	out, childOut, err := os.Pipe()
	if err != nil {
		_ = in.Close()
		_ = childIn.Close()
		cancel()
		return nil, ErrTransport
	}
	cmd.Stdin = childIn
	cmd.Stdout = childOut
	if err = ctx.Err(); err == nil {
		err = cmd.Start()
	}
	_ = childIn.Close()
	_ = childOut.Close()
	if err != nil {
		_ = in.Close()
		_ = out.Close()
		cancel()
		return nil, errors.New("could not start configured worker")
	}
	c := &Client{cmd: cmd, cancel: cancel, exited: make(chan struct{})}
	c.conn = jsonrpc2.NewConn(ctx, jsonrpc2.NewBufferedStream(&pipe{Reader: out, WriteCloser: in, reader: out}, jsonrpc2.VSCodeObjectCodec{}), jsonrpc2.AsyncHandler(receiver{c, handler}), jsonrpc2.SetLogger(quietLogger{}))
	go func() { _ = cmd.Wait(); close(c.exited) }()
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
