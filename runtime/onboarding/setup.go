package onboarding

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"strings"

	"github.com/pelletier/go-toml/v2"
	"golang.org/x/term"
	"loom/runtime/config"
	"loom/runtime/contracts"
	"loom/runtime/work"
)

type Setup struct {
	SandboxProvider, SandboxOptions                                        string
	SandboxFactories                                                       map[string]contracts.ProviderFactory
	ConfigPath, Provider, Model, ModelFile, ModelEndpoint, SandboxEndpoint string
	ModelKeyEnv, SandboxKeyEnv, ModelKeyFile, SandboxKeyFile               string
	Input                                                                  io.Reader
	Output                                                                 io.Writer
}

func (s Setup) Run(ctx context.Context) error {
	root, err := Assets()
	if err != nil {
		return err
	}
	worker, err := ModelWorker(root)
	if err != nil {
		return err
	}
	configPath, err := filepath.Abs(s.ConfigPath)
	if err != nil {
		return err
	}
	definitionPath := DefaultDefinition(configPath)
	for _, path := range []string{configPath, definitionPath} {
		if _, err = os.Lstat(path); !os.IsNotExist(err) {
			return errors.New("setup will not overwrite existing configuration; use --config with a new path or edit existing files")
		}
	}
	in, interactive := s.Input.(*os.File)
	interactive = interactive && term.IsTerminal(int(in.Fd()))
	reader := bufio.NewReader(s.Input)
	prompt := func(label, current string) (string, error) {
		if current != "" {
			return current, nil
		}
		if !interactive {
			return "", fmt.Errorf("%s is required in non-interactive setup", label)
		}
		fmt.Fprint(s.Output, label+": ")
		answer, err := reader.ReadString('\n')
		if err != nil {
			return "", errors.New("setup input ended")
		}
		answer = strings.TrimSpace(answer)
		if answer == "" {
			return "", fmt.Errorf("%s cannot be empty", label)
		}
		return answer, nil
	}
	var native CatalogModel
	if s.ModelFile != "" {
		data, err := os.ReadFile(s.ModelFile)
		if err != nil {
			return errors.New("cannot read custom native model file")
		}
		if err = json.Unmarshal(data, &native.Definition); err != nil {
			return errors.New("custom model must be a native Pi model JSON object without transport credentials")
		}
	} else {
		if interactive && s.Provider == "" {
			var providers []string
			if err = Catalog(ctx, root, nil, &providers); err != nil {
				return err
			}
			fmt.Fprintln(s.Output, "Providers: "+strings.Join(providers, ", "))
		}
		s.Provider, err = prompt("Provider (--provider)", s.Provider)
		if err != nil {
			return err
		}
		if interactive && s.Model == "" {
			var models []map[string]any
			if err = Catalog(ctx, root, []string{s.Provider}, &models); err != nil {
				return err
			}
			ids := []string{}
			for _, m := range models {
				ids = append(ids, fmt.Sprint(m["id"]))
			}
			fmt.Fprintln(s.Output, "Models: "+strings.Join(ids, ", "))
		}
		s.Model, err = prompt("Model (--model)", s.Model)
		if err != nil {
			return err
		}
		if err = Catalog(ctx, root, []string{s.Provider, s.Model}, &native); err != nil {
			return err
		}
	}
	if s.ModelEndpoint == "" {
		s.ModelEndpoint = native.Endpoint
	}
	s.ModelEndpoint, err = prompt("Model endpoint (--model-endpoint)", s.ModelEndpoint)
	if err != nil {
		return err
	}
	s.SandboxProvider, err = prompt("Sandbox provider (--sandbox-provider)", s.SandboxProvider)
	if err != nil {
		return err
	}
	if s.SandboxFactories[s.SandboxProvider] == nil {
		return errors.New("Sandbox provider is not registered in this release")
	}
	s.SandboxEndpoint, err = prompt("Sandbox endpoint (--sandbox-endpoint)", s.SandboxEndpoint)
	if err != nil {
		return err
	}
	u, err := url.Parse(s.ModelEndpoint)
	if err != nil || u == nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return errors.New("model endpoint must be an HTTP(S) URL without credentials")
	}
	u, err = url.Parse(s.SandboxEndpoint)
	if err != nil || u == nil || u.Scheme == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return errors.New("sandbox endpoint must be a credential-free URI; provider validates its transport")
	}
	definition, err := work.ReadDefinition(filepath.Join(root, "deploy/work.example.toml"))
	if err != nil {
		return err
	}
	definition.Model = work.ModelDefinition{Service: "primary", Parameters: native.Definition}
	if err = definition.Validate(); err != nil {
		return err
	}
	pendingSecrets := map[string][]byte{}
	secretRef := func(label, env, file string) (string, string, error) {
		if env != "" && file != "" {
			return "", "", errors.New("choose one key environment variable or private key file")
		}
		if env != "" {
			return env, "", nil
		}
		if file != "" {
			abs, err := filepath.Abs(file)
			if err != nil {
				return "", "", err
			}
			info, err := os.Lstat(abs)
			if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0 {
				return "", "", errors.New("key file must be private (0600) and regular")
			}
			return "", abs, nil
		}
		if !interactive {
			return "", "", fmt.Errorf("provide --%s-key-env or --%s-key-file in non-interactive setup", label, label)
		}
		fmt.Fprintf(s.Output, "%s API key (hidden): ", label)
		raw, err := term.ReadPassword(int(in.Fd()))
		fmt.Fprintln(s.Output)
		if err != nil || len(strings.TrimSpace(string(raw))) == 0 {
			return "", "", errors.New("empty or unreadable API key")
		}
		path := filepath.Join(filepath.Dir(configPath), "secrets", label+".key")
		if _, err = os.Lstat(path); !os.IsNotExist(err) {
			return "", "", errors.New("secret file already exists; use an explicit key reference")
		}
		pendingSecrets[path] = raw
		return "", path, nil
	}
	menv, mfile, err := secretRef("model", s.ModelKeyEnv, s.ModelKeyFile)
	if err != nil {
		return err
	}
	senv, sfile, err := secretRef("sandbox", s.SandboxKeyEnv, s.SandboxKeyFile)
	if err != nil {
		return err
	}
	example, err := config.Load(filepath.Join(root, "deploy/config.example.toml"))
	if err != nil {
		return err
	}
	profile := example.Profiles["code"]
	if s.SandboxOptions != "" {
		profile.Options = nil
		raw, err := os.ReadFile(s.SandboxOptions)
		if err != nil || json.Unmarshal(raw, &profile.Options) != nil || profile.Options == nil {
			return errors.New("sandbox-options must name a non-secret JSON object")
		}
	} else {
		matches := 0
		for _, preset := range example.Profiles {
			if example.Sandboxes[preset.Service].Provider == s.SandboxProvider {
				profile = preset
				matches++
			}
		}
		if matches != 1 {
			return errors.New("selected provider requires --sandbox-options; no unique preset is installed")
		}
	}
	// Setup creates one logical code service; preset names are deployment
	// examples, not identities to copy into a new user's configuration.
	profile.Service = "code"
	options, err := json.Marshal(profile.Options)
	if err != nil {
		return err
	}
	binding := contracts.Binding{Provider: s.SandboxProvider, ServiceID: profile.Service, Endpoint: strings.TrimRight(s.SandboxEndpoint, "/"), OptionsJSON: string(options)}
	client, err := s.SandboxFactories[s.SandboxProvider](binding, "setup-validation")
	if err != nil {
		return err
	}
	if client == nil || client.Binding() != binding {
		return errors.New("provider changed the configured binding")
	}
	facility, err := config.Facility()
	if err != nil {
		return err
	}
	if err = facility.Check(); err != nil {
		return err
	}
	host := config.Config{Profiles: map[string]config.SandboxProfile{"code": profile}, Models: map[string]config.ModelService{"primary": {Endpoint: s.ModelEndpoint, Worker: worker, APIKeyEnv: menv, APIKeyFile: mfile}}, Sandboxes: map[string]config.SandboxService{profile.Service: {Provider: s.SandboxProvider, Endpoint: s.SandboxEndpoint, APIKeyEnv: senv, APIKeyFile: sfile}}}
	hostBytes, err := toml.Marshal(host)
	if err != nil {
		return err
	}
	defBytes, err := toml.Marshal(definition)
	if err != nil {
		return err
	}
	written := []string{}
	completed := false
	defer func() {
		if !completed {
			for _, p := range written {
				os.Remove(p)
			}
		}
	}()
	save := func(path string, data []byte) error {
		if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
			return err
		}
		f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
		if err != nil {
			return err
		}
		written = append(written, path)
		if _, err = f.Write(data); err == nil {
			err = f.Sync()
		}
		closeErr := f.Close()
		if err != nil {
			return err
		}
		return closeErr
	}
	for path, secret := range pendingSecrets {
		if err = save(path, secret); err != nil {
			return errors.New("cannot save private credential file")
		}
	}
	if err = save(definitionPath, defBytes); err != nil {
		return err
	}
	if err = save(configPath, hostBytes); err != nil {
		return err
	}
	completed = true
	fmt.Fprintf(s.Output, "Configured %s\nWork defaults: %s\nNext: loom new /path/to/work --userspace /path/to/task-files\n", configPath, definitionPath)
	return nil
}
