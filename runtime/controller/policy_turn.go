package controller

import (
	"encoding/json"
	"loom/runtime/store"
	"os"
	"path/filepath"
)

// Native turn bodies are fixed data in the strategy's existing readonly source
// mount. Neither a provider-specific message nor a large history is an RPC frame.
func (c *run) policyTurn(turn Object) (Object, error) {
	if turn == nil {
		return Object{"turn": nil}, nil
	}
	raw, err := json.Marshal(turn)
	if err != nil {
		return nil, err
	}
	ref, err := (store.Records{Directory: c.work.ArtifactsDir()}).Put(raw, "application/json")
	if err != nil {
		return nil, err
	}
	// Repeated callbacks may reference the same native turn. Never truncate a
	// file already mounted into the running strategy, even to identical bytes.
	sourceRecords := store.Records{Directory: filepath.Join(c.domain.binding.Staging, "sources")}
	if _, err = sourceRecords.Put(raw, "application/json"); err != nil {
		return nil, err
	}
	path := filepath.Join(sourceRecords.Directory, ref.SHA256)
	if err = os.Chown(path, c.domain.scope.UID, c.domain.scope.GID); err != nil {
		return nil, err
	}
	return Object{"turn_path": "/sources/" + filepath.Base(path), "turn_ref": ref}, nil
}
