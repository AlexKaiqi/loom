package controller

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime/debug"
	"strconv"
)

func (c *run) interfaceView() Object {
	build := "development"
	if info, ok := debug.ReadBuildInfo(); ok {
		for _, setting := range info.Settings {
			if setting.Key == "vcs.revision" {
				build = setting.Value
			}
			if setting.Key == "vcs.modified" && setting.Value == "true" {
				build += "+modified"
			}
		}
	}
	return Object{"protocol_version": "loom/1", "schema_version": 1, "work_id": c.work.ID, "round_id": c.round.ID,
		"epoch": strconv.FormatInt(c.round.Epoch, 10), "harness_ref": c.round.HarnessRef, "runtime_build": build,
		"capabilities": []string{"context.feedback/1", "userspace.binding/1"}, "operations": harnessSchemas(),
		"role_permissions": Object{"harness": harnessOperations, "bash": []string{}},
		"tools":            c.policy.NativeTools(), "targets": c.work.Definition.Targets,
		"limitations": []string{"Schemas describe request syntax; resource grants and current custody are checked separately.", "Work Bash has no Runtime control channel. Candidate edits do not activate a strategy."}}
}
func (c *run) writeInterface(directory string, uid, gid int) error {
	raw, err := json.Marshal(c.interfaceView())
	if err != nil {
		return err
	}
	path := filepath.Join(directory, "interface.json")
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0400)
	if err != nil {
		return err
	}
	defer file.Close()
	if _, err = file.Write(raw); err != nil {
		return err
	}
	if err = file.Chown(uid, gid); err != nil {
		return err
	}
	return file.Sync()
}
