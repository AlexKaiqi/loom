// Package config resolves portable service names using host-only transports,
// credentials and worker installations. Work owns all model/environment semantics.
package config

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/pelletier/go-toml/v2"
	sandbox "loom/runtime/adapters/opensandbox"
	"loom/runtime/contracts"
	"loom/runtime/execution"
	"loom/runtime/work"
)

type Config struct {
	Execution *execution.Config                       `toml:"execution,omitempty"`
	Models    map[string]ModelService                 `toml:"models"`
	Profiles  map[string]contracts.TargetRequirements `toml:"profiles"`
	Sandboxes map[string]SandboxService               `toml:"sandboxes"`
}
type ModelService struct {
	Parameters map[string]any    `toml:"parameters"`
	Endpoint   string            `toml:"endpoint"`
	APIKeyEnv  string            `toml:"api_key_env,omitempty"`
	APIKeyFile string            `toml:"api_key_file,omitempty"`
	Worker     []string          `toml:"worker"`
	HeadersEnv map[string]string `toml:"headers_env"`
}
type SandboxService struct {
	Endpoint   string `toml:"endpoint"`
	APIKeyEnv  string `toml:"api_key_env,omitempty"`
	APIKeyFile string `toml:"api_key_file,omitempty"`
}
type ModelDeployment struct {
	Model  map[string]any
	APIKey string
	Worker []string
}

func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, errors.New("cannot read host service configuration")
	}
	var c Config
	if err = toml.NewDecoder(bytes.NewReader(data)).DisallowUnknownFields().Decode(&c); err != nil {
		return nil, errors.New("invalid host service configuration; expected named models and sandboxes")
	}
	if c.Execution == nil && os.Getenv("LOOM_EXECUTION_CONFIG") != "" {
		c.Execution, err = Facility()
		if err != nil {
			return nil, err
		}
	}
	return &c, nil
}

// Facility is private deployment configuration bound to the running release.
// Service configuration may outlive upgrades without pinning a different
// container's launcher binary or changing a process that already owns a Round.
func Facility() (*execution.Config, error) {
	path := os.Getenv("LOOM_EXECUTION_CONFIG")
	if path == "" {
		return nil, errors.New("shared Linux facility is not configured; use the installed launcher")
	}
	body, err := os.ReadFile(path)
	if err != nil {
		return nil, errors.New("cannot read facility execution binding")
	}
	var result execution.Config
	if err = toml.NewDecoder(bytes.NewReader(body)).DisallowUnknownFields().Decode(&result); err != nil {
		return nil, errors.New("invalid facility execution binding")
	}
	return &result, nil
}
func (c *Config) ResolveModel(def work.ModelDefinition) (*ModelDeployment, error) {
	return c.resolveModel(def, true)
}

// DescribeModel resolves declared semantics without opening credentials. A
// Harness can inspect inputs or hand off without dispatching a model request.
func (c *Config) DescribeModel(def work.ModelDefinition) (*ModelDeployment, error) {
	return c.resolveModel(def, false)
}

func (c *Config) resolveModel(def work.ModelDefinition, credentials bool) (*ModelDeployment, error) {
	service, ok := c.Models[def.Service]
	if !ok {
		return nil, fmt.Errorf("model service %q is not configured on this host", def.Service)
	}
	if len(service.Worker) == 0 {
		return nil, errors.New("model service worker argv is required")
	}
	if err := endpoint(service.Endpoint); err != nil {
		return nil, err
	}
	var key string
	var err error
	if credentials {
		key, err = credential(service.APIKeyEnv, service.APIKeyFile)
		if err != nil {
			return nil, err
		}
	}
	// A deep copy keeps host-only values out of the portable definition.
	merged := map[string]any{}
	for k, v := range service.Parameters {
		merged[k] = v
	}
	for k, v := range def.Parameters {
		merged[k] = v
	}
	if err := work.ValidateModelParameters(merged); err != nil {
		return nil, err
	}
	for _, key := range []string{"id", "api", "provider"} {
		if value, ok := merged[key].(string); !ok || value == "" {
			return nil, fmt.Errorf("model parameter %s required from Work or service", key)
		}
	}
	data, err := json.Marshal(merged)
	if err != nil {
		return nil, err
	}
	var native map[string]any
	if err = json.Unmarshal(data, &native); err != nil {
		return nil, err
	}
	if native == nil {
		return nil, errors.New("portable model definition is required")
	}
	native["baseUrl"] = service.Endpoint
	if credentials && len(service.HeadersEnv) > 0 {
		headers := map[string]string{}
		for name, env := range service.HeadersEnv {
			value, err := secret(env)
			if err != nil {
				return nil, err
			}
			headers[name] = value
		}
		native["headers"] = headers
	}
	return &ModelDeployment{Model: native, APIKey: key, Worker: append([]string(nil), service.Worker...)}, nil
}
func (c *Config) ResolveSandbox(def *contracts.TargetRequirements) (contracts.TaskExecutor, error) {
	if def == nil {
		return nil, nil
	}
	return c.ResolveSavedSandbox(sandbox.Binding{ServiceID: def.Service, Image: def.Image, Profile: def.Profile, CPU: def.CPU, Memory: def.Memory, LeaseSeconds: float64(def.LeaseSeconds), RequestTimeoutSeconds: float64(def.RequestTimeoutSeconds)})
}

// ResolveSavedSandbox retains the saved execution requirements, and rejects
// changed destinations before even constructing a client capable of querying it.
func (c *Config) ResolveSavedSandbox(binding sandbox.Binding) (contracts.TaskExecutor, error) {
	service, ok := c.Sandboxes[binding.ServiceID]
	if !ok {
		return nil, fmt.Errorf("sandbox service %q is not configured on this host", binding.ServiceID)
	}
	if binding.Endpoint != "" && binding.Endpoint != trimOrigin(service.Endpoint) {
		return nil, errors.New("saved sandbox endpoint does not match this host's service binding")
	}
	lease, err := seconds(binding.LeaseSeconds)
	if err != nil {
		return nil, err
	}
	timeout, err := seconds(binding.RequestTimeoutSeconds)
	if err != nil {
		return nil, err
	}
	if binding.Profile == "" || binding.CPU == "" || binding.Memory == "" {
		return nil, errors.New("explicit sandbox execution requirements are missing")
	}
	key, err := credential(service.APIKeyEnv, service.APIKeyFile)
	if err != nil {
		return nil, err
	}
	return sandbox.New(sandbox.Config{ServiceID: binding.ServiceID, Endpoint: service.Endpoint, APIKey: key, Image: binding.Image, Profile: binding.Profile, CPU: binding.CPU, Memory: binding.Memory, Lease: lease, RequestTimeout: timeout})
}
func trimOrigin(s string) string {
	if len(s) > 0 && s[len(s)-1] == '/' {
		return s[:len(s)-1]
	}
	return s
}
func endpoint(s string) error {
	u, err := url.Parse(s)
	if err != nil || u == nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return errors.New("model endpoint must be an HTTP(S) URL without credentials, query or fragment")
	}
	return nil
}
func seconds(n float64) (time.Duration, error) {
	if n <= 0 || math.IsNaN(n) || math.IsInf(n, 0) || n >= float64(math.MaxInt64)/float64(time.Second) {
		return 0, errors.New("sandbox duration must be explicit, positive and fit a duration")
	}
	return time.Duration(n * float64(time.Second)), nil
}
func secret(name string) (string, error) {
	if name == "" {
		return "", errors.New("credential environment variable name is required")
	}
	value := os.Getenv(name)
	if value == "" {
		return "", errors.New("required credential environment variable is missing: " + name)
	}
	return value, nil
}

// A key file is external host state. Never carry it into a Work or worker argv.
func credential(env, filename string) (string, error) {
	if env != "" && filename != "" {
		return "", errors.New("choose one credential reference: api_key_env or api_key_file")
	}
	if filename == "" {
		return secret(env)
	}
	if !filepath.IsAbs(filename) {
		return "", errors.New("credential file path must be absolute")
	}
	info, err := os.Lstat(filename)
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0 {
		return "", errors.New("credential file must be a private regular file (0600)")
	}
	data, err := os.ReadFile(filename)
	if err != nil {
		return "", errors.New("cannot read credential file")
	}
	value := strings.TrimSpace(string(data))
	if value == "" {
		return "", errors.New("credential file is empty")
	}
	return value, nil
}

func (c *Config) ResolveTargets(targets map[string]work.TargetDefinition) (map[string]contracts.TaskExecutor, error) {
	result := map[string]contracts.TaskExecutor{}
	for name, target := range targets {
		profile, ok := c.Profiles[target.Profile]
		if !ok {
			return nil, fmt.Errorf("capability_missing: Target %s profile %s is unavailable", name, target.Profile)
		}
		executor, err := c.ResolveSandbox(&profile)
		if err != nil {
			return nil, err
		}
		result[name] = executor
	}
	return result, nil
}
