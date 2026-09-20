package controller

import (
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"errors"
	"net/url"
	"os"
	"path/filepath"
	"strings"
)

// Validate attribution against the same immutable, authorized sources supplied
// to the strategy. This validates provenance, not the strategy's business
// interpretation or token accounting. Total capacity uses actual input bytes.
func (c *run) validateSources(candidate Object, basis projectionBasis) error {
	sources := arrayObjects(candidate["sources"])
	if len(sources) == 0 {
		return nil
	}
	c.api.mu.Lock()
	view, ok := c.api.views[basis.ViewID]
	c.api.mu.Unlock()
	if !ok || c.domain == nil {
		return errors.New("permission_denied: source view unavailable")
	}
	uri := url.URL{Scheme: "file", Path: filepath.Join(view.Directory, "facts.sqlite"), RawQuery: "mode=ro"}
	db, err := sql.Open("sqlite", uri.String())
	if err != nil {
		return err
	}
	defer db.Close()
	for _, source := range sources {
		count, err := number(source["utf8_bytes"])
		if err != nil || count < 0 {
			return errors.New("invalid_request: source byte estimate")
		}
		switch source["kind"] {
		case "facts":
			ids, ok := source["fact_ids"].([]any)
			if !ok || len(ids) == 0 {
				return errors.New("invalid_request: source fact ids")
			}
			for _, raw := range ids {
				id, ok := raw.(string)
				if !ok {
					return errors.New("invalid_request: source fact id")
				}
				var n int
				if err = db.QueryRow("SELECT count(*) FROM facts WHERE fact_id=?", id).Scan(&n); err != nil {
					return err
				}
				if n != 1 {
					return errors.New("permission_denied: source fact outside view")
				}
			}
		case "template", "file":
			path, ok := source["path"].(string)
			if !ok || path == "." || filepath.IsAbs(path) || filepath.Clean(path) != path || strings.HasPrefix(path, "../") {
				return errors.New("permission_denied: source path")
			}
			root := filepath.Join(c.domain.binding.Staging, "sources", basis.ContentRef)
			if alias, ok := source["resource"].(string); ok {
				target := "source"
				if value, ok := source["target"].(string); ok {
					target = value
				}
				bindings := object(basis.Resources[alias])
				binding := object(bindings[target])
				mount, _ := binding["root"].(string)
				if !strings.HasPrefix(mount, "/resources/") || filepath.Dir(mount) != "/resources" {
					return errors.New("permission_denied: source resource")
				}
				root = filepath.Join(c.domain.binding.Staging, "resources", filepath.Base(mount))
			}
			filesystem, err := os.OpenRoot(root)
			if err != nil {
				return err
			}
			raw, err := filesystem.ReadFile(path)
			filesystem.Close()
			if err != nil {
				return errors.New("dependency_missing: source file")
			}
			digest := sha256.Sum256(raw)
			if hex.EncodeToString(digest[:]) != source["sha256"] {
				return errors.New("baseline_conflict: source file digest")
			}
		default:
			return errors.New("capability_missing: source attribution kind")
		}
	}
	return nil
}
