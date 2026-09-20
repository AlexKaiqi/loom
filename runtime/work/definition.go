package work

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"regexp"
	"strings"

	"github.com/pelletier/go-toml/v2"
)

// Definition contains portable requirements, never deployment routes or authority.
type Definition struct {
	Model     ModelDefinition      `toml:"model" json:"model"`
	Sandbox   *SandboxDefinition   `toml:"sandbox,omitempty" json:"sandbox,omitempty"`
	Userspace *UserspaceDefinition `toml:"userspace,omitempty" json:"userspace,omitempty"`
}
type ModelDefinition struct {
	Service    string         `toml:"service" json:"service"`
	Definition map[string]any `toml:"definition" json:"definition"`
}
type SandboxDefinition struct {
	Service               string `toml:"service" json:"service"`
	Image                 string `toml:"image" json:"image"`
	Profile               string `toml:"profile" json:"profile"`
	CPU                   string `toml:"cpu" json:"cpu"`
	Memory                string `toml:"memory" json:"memory"`
	LeaseSeconds          int    `toml:"lease_seconds" json:"lease_seconds"`
	RequestTimeoutSeconds int    `toml:"request_timeout_seconds" json:"request_timeout_seconds"`
}
type UserspaceDefinition struct {
	Name string `toml:"name" json:"name"`
}

var logicalName = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]*$`)
var pinnedImage = regexp.MustCompile(`^\S+@sha256:[a-fA-F0-9]{64}$`)

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
	if err := d.Validate(); err != nil {
		return d, err
	}
	return d, nil
}
func (d Definition) Validate() error {
	if !logicalName.MatchString(d.Model.Service) {
		return errors.New("Work requires a named model service")
	}
	for _, key := range []string{"id", "api", "provider"} {
		if s, ok := d.Model.Definition[key].(string); !ok || s == "" {
			return fmt.Errorf("model.definition.%s is required", key)
		}
	}
	allowed := map[string]bool{"id": true, "name": true, "api": true, "provider": true, "reasoning": true, "input": true, "cost": true, "contextWindow": true, "maxTokens": true, "compat": true}
	for key := range d.Model.Definition {
		if !allowed[key] {
			return fmt.Errorf("unsupported portable model field %q; transport and credentials belong to the host service", key)
		}
	}
	if err := portableModelValues(d.Model.Definition); err != nil {
		return err
	}
	if d.Sandbox != nil {
		s := d.Sandbox
		if !logicalName.MatchString(s.Service) || !pinnedImage.MatchString(s.Image) || s.Profile != "code" {
			return errors.New("Sandbox requires named service, digest-pinned image and code profile")
		}
		if s.CPU == "" || s.Memory == "" || s.LeaseSeconds <= 0 || s.RequestTimeoutSeconds <= 0 {
			return errors.New("Sandbox CPU, memory, lease_seconds and request_timeout_seconds must be explicit")
		}
	}
	if d.Userspace != nil && !logicalName.MatchString(d.Userspace.Name) {
		return errors.New("Userspace requires a logical name")
	}
	return nil
}
func portableModelValues(value any) error {
	switch v := value.(type) {
	case map[string]any:
		for key, child := range v {
			normalized := strings.NewReplacer("_", "", "-", "").Replace(strings.ToLower(key))
			for _, forbidden := range []string{"apikey", "secret", "password", "credential", "headers", "baseurl", "endpoint", "worker", "environment", "env"} {
				if strings.Contains(normalized, forbidden) {
					return fmt.Errorf("model field %q belongs to host deployment, not Work", key)
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
