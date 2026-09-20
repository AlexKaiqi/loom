package work

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"github.com/pelletier/go-toml/v2"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// Definition is the current public work.toml schema. Deployment routes, physical
// identities, credentials and profile implementations remain host authority.
type Definition struct {
	SchemaVersion int                            `toml:"schema_version" json:"schema_version"`
	Harness       HarnessDefinition              `toml:"harness" json:"harness"`
	Surface       SurfaceDefinition              `toml:"surface" json:"surface"`
	Model         ModelDefinition                `toml:"model" json:"model"`
	Userspaces    map[string]UserspaceDefinition `toml:"userspaces,omitempty" json:"userspaces,omitempty"`
	Targets       map[string]TargetDefinition    `toml:"targets,omitempty" json:"targets,omitempty"`
	Extensions    map[string]any                 `toml:"extensions,omitempty" json:"extensions,omitempty"`
}
type HarnessDefinition struct {
	Path string   `toml:"path" json:"path"`
	Argv []string `toml:"argv" json:"argv"`
}
type SurfaceDefinition struct {
	Path string `toml:"path" json:"path"`
}
type ModelDefinition struct {
	Service    string         `toml:"service" json:"service"`
	Parameters map[string]any `toml:"parameters" json:"parameters"`
}
type UserspaceDefinition struct {
	Resource string `toml:"resource" json:"resource"`
	Access   string `toml:"access" json:"access"`
	Delivery string `toml:"delivery,omitempty" json:"delivery,omitempty"`
}
type TargetDefinition struct {
	Profile    string   `toml:"profile" json:"profile"`
	Userspaces []string `toml:"userspaces,omitempty" json:"userspaces,omitempty"`
}

var logicalName = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]*$`)

func ReadDefinition(path string) (Definition, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return Definition{}, err
	}
	return parseDefinition(data)
}
func parseDefinition(data []byte) (Definition, error) {
	var d Definition
	if err := toml.NewDecoder(bytes.NewReader(data)).DisallowUnknownFields().Decode(&d); err != nil {
		return d, fmt.Errorf("invalid Work definition: %w", err)
	}
	return d, d.Validate()
}
func logicalRoot(path string) bool {
	return path != "" && path != "." && !filepath.IsAbs(path) && filepath.Clean(path) == path && !strings.Contains(path, "\\") && path != ".." && !strings.HasPrefix(path, "../") && path != ".loom" && !strings.HasPrefix(path, ".loom/") && path != "work.toml"
}
func (d Definition) Validate() error {
	if d.SchemaVersion != 2 {
		return errors.New("unsupported Work configuration: schema_version=2 required")
	}
	if !logicalRoot(d.Harness.Path) || !logicalRoot(d.Surface.Path) || d.Harness.Path == d.Surface.Path || strings.HasPrefix(d.Harness.Path, d.Surface.Path+"/") || strings.HasPrefix(d.Surface.Path, d.Harness.Path+"/") {
		return errors.New("Harness and Surface require separate normalized Work-relative roots")
	}
	if len(d.Harness.Argv) == 0 || d.Harness.Argv[0] == "" {
		return errors.New("harness.argv must be a nonempty executable argument array")
	}
	for _, arg := range d.Harness.Argv {
		if strings.ContainsRune(arg, 0) {
			return errors.New("invalid Harness argv")
		}
	}
	if !logicalName.MatchString(d.Model.Service) {
		return errors.New("Work requires a named model service")
	}
	if err := ValidateModelParameters(d.Model.Parameters); err != nil {
		return err
	}
	for alias, u := range d.Userspaces {
		if !logicalName.MatchString(alias) || !logicalName.MatchString(u.Resource) || (u.Access != "read" && u.Access != "write") || (u.Delivery != "" && u.Delivery != "per-tool") {
			return fmt.Errorf("invalid Userspace declaration %q", alias)
		}
	}
	for name, target := range d.Targets {
		if !logicalName.MatchString(name) || !logicalName.MatchString(target.Profile) {
			return errors.New("Target requires logical name and profile")
		}
		seen := map[string]bool{}
		for _, alias := range target.Userspaces {
			if _, ok := d.Userspaces[alias]; !ok || seen[alias] {
				return errors.New("Target contains unknown or duplicate Userspace alias")
			}
			seen[alias] = true
		}
	}
	return nil
}
func ValidateModelParameters(params map[string]any) error {
	allowed := map[string]bool{"id": true, "name": true, "api": true, "provider": true, "reasoning": true, "input": true, "cost": true, "contextWindow": true, "maxTokens": true, "compat": true}
	for key := range params {
		if !allowed[key] {
			return fmt.Errorf("unsupported explicit model parameter %q", key)
		}
	}
	return portableModelValues(params)
}
func portableModelValues(value any) error {
	switch v := value.(type) {
	case map[string]any:
		for key, child := range v {
			normalized := strings.NewReplacer("_", "", "-", "").Replace(strings.ToLower(key))
			for _, forbidden := range []string{"apikey", "secret", "password", "credential", "headers", "baseurl", "endpoint", "worker", "environment", "env"} {
				if strings.Contains(normalized, forbidden) {
					return fmt.Errorf("model field %q belongs to host deployment", key)
				}
			}
			if err := portableModelValues(child); err != nil {
				return err
			}
		}
	case []any:
		for _, child := range v {
			if err := portableModelValues(child); err != nil {
				return err
			}
		}
	}
	return nil
}
func digestBytes(data []byte) string { sum := sha256.Sum256(data); return hex.EncodeToString(sum[:]) }
