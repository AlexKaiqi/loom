package main

import (
	"loom/runtime/adapters/opensandbox"
	"loom/runtime/adapters/sshprocess"
	"loom/runtime/config"
	"loom/runtime/contracts"
)

// This is the sole production registration point for concrete task providers.
func sandboxResolver(host *config.Config) *config.SandboxResolver {
	return host.SandboxResolver(sandboxFactories())
}

func sandboxFactories() map[string]contracts.ProviderFactory {
	return map[string]contracts.ProviderFactory{
		opensandbox.Provider: opensandbox.Open,
		sshprocess.Provider:  sshprocess.Open,
	}
}
