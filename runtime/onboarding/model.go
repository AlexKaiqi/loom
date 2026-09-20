package onboarding

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

type CatalogModel struct {
	Endpoint   string         `json:"endpoint"`
	Definition map[string]any `json:"definition"`
}

func Catalog(ctx context.Context, root string, args []string, out any) error {
	ctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "node", append([]string{filepath.Join(root, "services/model/catalog.mjs")}, args...)...)
	// Catalog lookup is local and does not need user credentials.
	for _, key := range []string{"PATH", "LANG", "LC_ALL", "TMPDIR"} {
		if val, ok := os.LookupEnv(key); ok {
			cmd.Env = append(cmd.Env, key+"="+val)
		}
	}
	data, err := cmd.Output()
	if err != nil {
		return errors.New("Pi model catalog lookup failed; check provider/model or use --model-file for a custom model")
	}
	if err = json.Unmarshal(data, out); err != nil {
		return errors.New("invalid Pi model catalog response")
	}
	return nil
}
