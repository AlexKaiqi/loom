package contracts

// TargetRequirements is a concrete host profile snapshot. It is retained with
// the allocation and effects, never resolved again for an existing native ID.
type TargetRequirements struct {
	Service               string `toml:"service" json:"service"`
	Image                 string `toml:"image" json:"image"`
	Profile               string `toml:"profile" json:"profile"`
	CPU                   string `toml:"cpu" json:"cpu"`
	Memory                string `toml:"memory" json:"memory"`
	LeaseSeconds          int    `toml:"lease_seconds" json:"lease_seconds"`
	RequestTimeoutSeconds int    `toml:"request_timeout_seconds" json:"request_timeout_seconds"`
}
