// Package onboarding assembles existing components; it owns no Runtime effects.
package onboarding

import (
	"errors"
	"os"
	"path/filepath"
)

func Assets() (string, error) {
	if root := os.Getenv("LOOM_INSTALL_ROOT"); root != "" {
		root, err := filepath.Abs(root)
		if err != nil {
			return "", err
		}
		if regular(filepath.Join(root, "services/model/worker.mjs")) {
			return root, nil
		}
		return "", errors.New("installed Loom components are missing; run install.sh again")
	}
	// Source builds remain useful to developers. No absolute build-machine path
	// is compiled into the binary or copied to a portable Work.
	exe, err := os.Executable()
	if err != nil {
		return "", err
	}
	exe, err = filepath.EvalSymlinks(exe)
	if err != nil {
		return "", err
	}
	candidate := filepath.Clean(filepath.Join(filepath.Dir(exe), "../.."))
	if regular(filepath.Join(candidate, "services/model/worker.mjs")) {
		return candidate, nil
	}
	return "", errors.New("cannot locate installed components; use the installed loom launcher")
}
func regular(path string) bool { i, e := os.Stat(path); return e == nil && i.Mode().IsRegular() }
func DefaultDefinition(configPath string) string {
	return filepath.Join(filepath.Dir(configPath), "work-default.toml")
}

// ModelWorker names a deployed component. The installed launcher binds PATH to
// its own release, so changing current never switches an already running process.
// Source builds retain an explicit worker path for developer deployment.
func ModelWorker(root string) ([]string, error) {
	if os.Getenv("LOOM_INSTALL_ROOT") != "" {
		info, err := os.Stat(filepath.Join(root, "bin/loom-model"))
		if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0111 == 0 {
			return nil, errors.New("installed model launcher is missing; run install.sh again")
		}
		return []string{"loom-model"}, nil
	}
	return []string{"node", filepath.Join(root, "services/model/worker.mjs")}, nil
}
