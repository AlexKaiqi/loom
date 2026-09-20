package rpc

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func fixture(t *testing.T) string {
	t.Helper()
	module, err := filepath.Abs("../../services/model/transport.mjs")
	if err != nil {
		t.Fatal(err)
	}
	body := `
import {createWorkerConnection} from MODULE;
const c=createWorkerConnection("model");
c.onRequest('ready',()=>true);
c.onRequest('unread',()=>{setTimeout(()=>{for(const h of process._getActiveHandles()) if(h.fd===3) h.pause();},10);return true;});
c.onRequest('nested', async p=>({answer:await c.sendRequest('custody',p),secret:process.env.LOOM_TEST_SECRET??null}));
c.onRequest('crash',()=>process.exit(17));
c.onRequest('delay',()=>new Promise(()=>{}));
c.listen();
`
	encoded, _ := json.Marshal(module)
	body = strings.Replace(body, "MODULE", string(encoded), 1)
	path := filepath.Join(t.TempDir(), "worker.mjs")
	if err = os.WriteFile(path, []byte(body), 0600); err != nil {
		t.Fatal(err)
	}
	return path
}
func TestBidirectionalCustodyAndEnvironment(t *testing.T) {
	t.Setenv("LOOM_TEST_SECRET", "must-not-inherit")
	var confirmed atomic.Bool
	worker := fixture(t)
	c, err := Start(context.Background(), []string{"node", worker}, "", func(ctx context.Context, method string, raw json.RawMessage) (any, error) {
		if method != "custody" {
			t.Error("unexpected callback")
		}
		var body map[string]any
		if err := Decode(raw, &body); err != nil {
			return nil, err
		}
		if body["large"].(json.Number).String() != "9007199254740991" {
			t.Error("native number changed")
		}
		confirmed.Store(true)
		return "durable", nil
	}, "model")
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	var result map[string]any
	if err = c.Call(ctx, "nested", map[string]any{"large": json.Number("9007199254740991")}, &result); err != nil {
		t.Fatal(err)
	}
	if !confirmed.Load() || result["answer"] != "durable" || result["secret"] != nil {
		t.Fatalf("invalid callback order or environment: %+v", result)
	}
}
func TestCallbackFailureAndWorkerDeath(t *testing.T) {
	for _, method := range []string{"nested", "crash", "delay"} {
		t.Run(method, func(t *testing.T) {
			c, err := Start(context.Background(), []string{"node", fixture(t)}, "", func(context.Context, string, json.RawMessage) (any, error) {
				return nil, errors.New("private credential should not echo")
			}, "model")
			if err != nil {
				t.Fatal(err)
			}
			defer c.Close()
			ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
			defer cancel()
			var ready bool
			if err = c.Call(ctx, "ready", nil, &ready); err != nil || !ready {
				t.Fatalf("fixture did not start: %v", err)
			}
			err = c.Call(ctx, method, map[string]any{}, nil)
			if !errors.Is(err, ErrTransport) {
				t.Fatalf("uncertain worker result not rejected: %v", err)
			}
			if strings.Contains(err.Error(), "private credential") {
				t.Fatal("callback secret echoed")
			}
		})
	}
}
func TestDecodeRejectsTrailingAndPreservesNumbers(t *testing.T) {
	var value map[string]any
	if err := Decode([]byte(`{"seq":9007199254740993}`), &value); err != nil {
		t.Fatal(err)
	}
	if value["seq"].(json.Number).String() != "9007199254740993" {
		t.Fatal("number precision lost")
	}
	if err := Decode([]byte(`{} {}`), &value); err == nil {
		t.Fatal("trailing JSON accepted")
	}
}

func TestDeadlineInterruptsUnreadPipe(t *testing.T) {
	c, err := Start(context.Background(), []string{"node", fixture(t)}, "", nil, "model")
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	if err = c.Call(context.Background(), "unread", nil, nil); err != nil {
		t.Fatal(err)
	}
	time.Sleep(30 * time.Millisecond)
	start := time.Now()
	finished := make(chan error, 1)
	go func() { finished <- c.Call(ctx, "large", map[string]any{"data": strings.Repeat("x", 2<<20)}, nil) }()
	select {
	case err = <-finished:
		if !errors.Is(err, ErrTransport) {
			t.Fatalf("expected unknown transport: %v", err)
		}
	case <-time.After(time.Second):
		c.Close()
		t.Fatal("deadline did not interrupt blocked pipe write")
	}
	if time.Since(start) > 800*time.Millisecond {
		t.Fatal("transport deadline required watchdog")
	}
}
