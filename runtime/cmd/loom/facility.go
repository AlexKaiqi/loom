package main

import (
	"context"
	"errors"
	"fmt"
	"os/exec"
	"time"

	"github.com/spf13/cobra"
	"loom/runtime/config"
)

func facilityCommand() *cobra.Command {
	return &cobra.Command{Use: "check-facility", Short: "Probe the configured Linux Work isolation and Python toolchain", Args: cobra.NoArgs, RunE: func(cmd *cobra.Command, _ []string) error {
		cfg, err := config.Facility()
		if err != nil {
			return err
		}
		if err = cfg.Check(); err != nil {
			return err
		}
		id := fmt.Sprintf("probe-%d", time.Now().UnixNano())
		scope, err := cfg.NewScope(id, "bash", cfg.UIDBase, cfg.UIDBase)
		if err != nil {
			return err
		}
		probe := `import errno, os, pathlib, socket
from pylsp_jsonrpc.endpoint import Endpoint
assert os.getuid() != 0
assert not pathlib.Path('/var/lib/loom-host').exists()
assert not pathlib.Path('/var/run/docker.sock').exists()
status = pathlib.Path('/proc/self/status').read_text()
assert status.split('NoNewPrivs:')[1].split()[0] == '1'
for name in ('CapEff', 'CapPrm', 'CapAmb'):
 assert int(status.split(name+':')[1].split()[0], 16) == 0
s = socket.socket(); s.settimeout(.2)
assert s.connect_ex(('1.1.1.1',443)) == errno.ENETUNREACH
print('Work isolation and Python RPC ready')`
		argv, runErr := scope.Command([]string{"python3", "-I", "-c", probe}, nil, "/tmp", 10)
		if runErr == nil {
			process := exec.CommandContext(cmd.Context(), argv[0], argv[1:]...)
			process.Stdout, process.Stderr = cmd.OutOrStdout(), cmd.ErrOrStderr()
			runErr = process.Run()
		}
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		return errors.Join(runErr, scope.Remove(ctx))
	}}
}
