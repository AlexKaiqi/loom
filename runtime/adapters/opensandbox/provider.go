package opensandbox

import (
	"encoding/json"
	"errors"
	"math"
	"strings"
	"time"

	"loom/runtime/contracts"
)

const Provider = "opensandbox/v1"

// Options belongs to this adapter, never to Runtime or the host resolver.
type Options struct {
	Image                 string  `json:"image"`
	Profile               string  `json:"profile"`
	CPU                   string  `json:"cpu"`
	Memory                string  `json:"memory"`
	LeaseSeconds          float64 `json:"lease_seconds"`
	RequestTimeoutSeconds float64 `json:"request_timeout_seconds"`
}

func seconds(n float64) (time.Duration, error) {
	if n <= 0 || math.IsNaN(n) || math.IsInf(n, 0) || n >= float64(math.MaxInt64)/float64(time.Second) {
		return 0, errors.New("sandbox duration must be explicit, positive and fit a duration")
	}
	return time.Duration(n * float64(time.Second)), nil
}

// Open is registered only by the executable's composition root. It validates
// the saved version and complete parameters before constructing an SDK client.
func Open(binding contracts.Binding, key string) (contracts.TaskExecutor, error) {
	if binding.Provider != Provider {
		return nil, errors.New("unsupported OpenSandbox binding version")
	}
	var options Options
	decoder := json.NewDecoder(strings.NewReader(binding.OptionsJSON))
	decoder.DisallowUnknownFields()
	if !json.Valid([]byte(binding.OptionsJSON)) || decoder.Decode(&options) != nil {
		return nil, errors.New("invalid OpenSandbox provider options")
	}
	lease, err := seconds(options.LeaseSeconds)
	if err != nil {
		return nil, err
	}
	timeout, err := seconds(options.RequestTimeoutSeconds)
	if err != nil {
		return nil, err
	}
	if options.Profile == "" || options.CPU == "" || options.Memory == "" {
		return nil, errors.New("explicit OpenSandbox execution requirements are missing")
	}
	client, err := New(Config{ServiceID: binding.ServiceID, Endpoint: binding.Endpoint, APIKey: key, Image: options.Image, Profile: options.Profile, CPU: options.CPU, Memory: options.Memory, Lease: lease, RequestTimeout: timeout})
	if err != nil {
		return nil, err
	}
	// Preserve the original non-secret snapshot byte for byte when recovering.
	client.binding = binding
	return client, nil
}
