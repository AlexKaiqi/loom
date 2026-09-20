// This executable exists only in independent tests, never in product builds.
package main

import (
	"context"
	"database/sql/driver"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"sync/atomic"
	"syscall"
	"time"

	"loom/runtime/rpc"
	"loom/runtime/store"
	"modernc.org/sqlite"
)

func main() {
	if len(os.Args) != 3 {
		panic("driver MODE DB")
	}
	mode, path := os.Args[1], os.Args[2]
	if mode == "rpc-stall" {
		client, err := rpc.Start(context.Background(), []string{path, "-e", "setInterval(()=>{},100000)"}, "", nil)
		if err != nil {
			panic(err)
		}
		defer client.Close()
		var watchdog atomic.Bool
		timer := time.AfterFunc(3*time.Second, func() { watchdog.Store(true); client.Close() })
		defer timer.Stop()
		ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
		defer cancel()
		started := time.Now()
		var result any
		err = client.Call(ctx, "test.stall", map[string]any{"data": strings.Repeat("x", 2<<20)}, &result)
		_ = json.NewEncoder(os.Stdout).Encode(map[string]any{"failed": err != nil, "elapsed_ms": time.Since(started).Milliseconds(), "watchdog": watchdog.Load()})
		return
	}
	if mode == "kill" {
		sqlite.MustRegisterScalarFunction("acceptance_kill_writer", 0, func(_ *sqlite.FunctionContext, _ []driver.Value) (driver.Value, error) {
			// This call is reached by the AFTER INSERT trigger, not by a timer.
			fmt.Fprintln(os.Stdout, "AFTER EVENT INSERT: SIGKILL")
			_ = os.Stdout.Sync()
			_ = syscall.Kill(os.Getpid(), syscall.SIGKILL)
			select {}
		})
	}
	events := store.Events{Path: path}
	control := store.Control{Path: path}
	var result any
	var err error
	switch mode {
	case "admit", "kill":
		result, err = events.Admit("independent-driver", "one", "work.objective.set", store.Object{"text": "one"})
	case "begin":
		result, err = control.BeginRound(fmt.Sprint(os.Getpid()))
	case "resume":
		result, err = control.ResumeRound(fmt.Sprint(os.Getpid()))
	default:
		panic("unknown mode")
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if err := json.NewEncoder(os.Stdout).Encode(result); err != nil {
		panic(err)
	}
}
