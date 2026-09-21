package taskio

import (
	"encoding/json"
	"errors"
	"loom/runtime/contracts"
	"slices"
	"strconv"
	"strings"
)

func ParseReadiness(raw string, readOnly []string) (*contracts.Readiness, error) {
	var report contracts.Readiness
	if err := json.Unmarshal([]byte(raw), &report); err != nil {
		return nil, errors.New("not_ready: code profile probe returned invalid evidence")
	}
	valid := report.Platform == "linux" && report.Architecture != "" &&
		strings.HasPrefix(report.Shell, "GNU bash, version ") && report.Tools["python"] != "" &&
		report.UID == 65534 && report.GID == 65534 && report.NoNewPrivs &&
		report.Network == "denied" && report.Workspace == "/workspace/task" &&
		slices.Equal(report.ReadOnlyPaths, readOnly)
	// The bounding set is a ceiling, not a granted capability. An empty
	// permitted/inheritable/ambient set plus NoNewPrivs prevents acquiring it.
	// Retain the measured ceiling without mistaking it for effective authority.
	_, boundErr := strconv.ParseUint(report.Capabilities["CapBnd"], 16, 64)
	valid = valid && boundErr == nil
	for _, name := range []string{"CapEff", "CapPrm", "CapInh", "CapAmb"} {
		valid = valid && report.Capabilities[name] == "0000000000000000"
	}
	if !valid {
		return nil, errors.New("not_ready: code profile capabilities or permissions do not satisfy requirements")
	}
	return &report, nil
}
