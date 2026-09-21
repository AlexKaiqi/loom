package config

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"strings"

	"loom/runtime/contracts"
	"loom/runtime/work"
)

// SandboxResolver contains only host policy and injected constructors. Adapter
// registration is deliberately explicit and never uses package init functions.
type SandboxResolver struct {
	host      *Config
	factories map[string]contracts.ProviderFactory
}

func (c *Config) SandboxResolver(factories map[string]contracts.ProviderFactory) *SandboxResolver {
	copy := make(map[string]contracts.ProviderFactory, len(factories))
	for name, factory := range factories {
		copy[name] = factory
	}
	return &SandboxResolver{host: c, factories: copy}
}

func (r *SandboxResolver) ResolveTargets(targets map[string]work.TargetDefinition) (map[string]contracts.TaskExecutor, error) {
	result := map[string]contracts.TaskExecutor{}
	for name, target := range targets {
		profile, ok := r.host.Profiles[target.Profile]
		if !ok {
			return nil, fmt.Errorf("capability_missing: Target %s profile %s is unavailable", name, target.Profile)
		}
		service, ok := r.host.Sandboxes[profile.Service]
		if !ok {
			return nil, fmt.Errorf("sandbox service %q is not configured on this host", profile.Service)
		}
		if profile.Options == nil {
			return nil, errors.New("explicit sandbox provider options are required")
		}
		options, err := json.Marshal(profile.Options)
		if err != nil {
			return nil, errors.New("invalid sandbox provider options")
		}
		binding := contracts.Binding{Provider: service.Provider, ServiceID: profile.Service, Endpoint: strings.TrimRight(service.Endpoint, "/"), OptionsJSON: string(options)}
		executor, err := r.ResolveSavedSandbox(binding)
		if err != nil {
			return nil, err
		}
		result[name] = executor
	}
	return result, nil
}

// ResolveSavedSandbox never reads a current Profile. Old effects remain bound
// to the provider, endpoint and complete options selected before dispatch.
func (r *SandboxResolver) ResolveSavedSandbox(binding contracts.Binding) (contracts.TaskExecutor, error) {
	if binding.Provider == "" || binding.ServiceID == "" || binding.Endpoint == "" {
		return nil, errors.New("saved sandbox binding requires provider, service and endpoint; use the original release for old bindings")
	}
	service, ok := r.host.Sandboxes[binding.ServiceID]
	if !ok {
		return nil, fmt.Errorf("sandbox service %q is not configured on this host", binding.ServiceID)
	}
	if service.Provider != binding.Provider || strings.TrimRight(service.Endpoint, "/") != binding.Endpoint {
		return nil, errors.New("saved sandbox provider or endpoint does not match this host's service binding")
	}
	factory := r.factories[binding.Provider]
	if factory == nil {
		return nil, fmt.Errorf("capability_missing: sandbox provider %q is not registered", binding.Provider)
	}
	endpoint, err := url.Parse(binding.Endpoint)
	if err != nil || endpoint.Scheme == "" || endpoint.User != nil || endpoint.RawQuery != "" || endpoint.Fragment != "" {
		return nil, errors.New("sandbox endpoint must be a credential-free URI; provider validates its transport")
	}
	var options map[string]any
	if json.Unmarshal([]byte(binding.OptionsJSON), &options) != nil || options == nil {
		return nil, errors.New("saved sandbox provider options must be a JSON object")
	}
	// Empty credentials are permitted only if the selected adapter permits them.
	key := ""
	if service.APIKeyEnv != "" || service.APIKeyFile != "" {
		key, err = credential(service.APIKeyEnv, service.APIKeyFile)
		if err != nil {
			return nil, err
		}
	}
	executor, err := factory(binding, key)
	if err != nil {
		return nil, err
	}
	if executor == nil || executor.Binding() != binding {
		return nil, errors.New("sandbox provider factory changed the saved binding")
	}
	return executor, nil
}
