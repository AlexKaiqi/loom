package main

import (
	"github.com/AlexKaiqi/ondemand-sandbox/execution/contracts"
	"github.com/AlexKaiqi/ondemand-sandbox/execution/providers/opensandbox"
	"github.com/AlexKaiqi/ondemand-sandbox/execution/providers/sshprocess"
	"loom/runtime/config"
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
