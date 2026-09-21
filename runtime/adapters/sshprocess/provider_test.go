package sshprocess

import (
	"context"
	"encoding/json"
	"loom/runtime/contracts"
	"testing"
)

func TestFactoryValidatesCompleteDestinationWithoutEffects(t *testing.T) {
	o := Options{User: "root", HostKey: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC7LmtN3qwXIKV28t4MvpArNBnYhzsAnOavWTfrGO+wL", StateDirectory: "/var/lib/loom-process", NsJail: "/usr/local/bin/nsjail", NsJailSHA256: digest("fixture"), MemoryBytes: 536870912, Processes: 64, CPUPercent: 100, LeaseSeconds: 600, RequestTimeoutSeconds: 30}
	b, _ := json.Marshal(o)
	binding := contracts.Binding{Provider: Provider, ServiceID: "fixture", Endpoint: "ssh://unreachable.invalid:22", OptionsJSON: string(b)}
	x, e := Open(binding, "setup-validation")
	if e != nil || x.Binding() != binding {
		t.Fatal("constructor performed effects or changed binding", e)
	}
	for _, edit := range []func(*contracts.Binding){func(b *contracts.Binding) { b.Provider = "ssh-process/v0" }, func(b *contracts.Binding) { b.Endpoint = "ssh://user:secret@host" }, func(b *contracts.Binding) { b.Endpoint = "http://host" }, func(b *contracts.Binding) { b.OptionsJSON = `{}` }, func(b *contracts.Binding) { b.OptionsJSON = `{"unknown":1}` }} {
		bad := binding
		edit(&bad)
		if _, e = Open(bad, "setup-validation"); e == nil {
			t.Fatal("invalid destination accepted", bad)
		}
	}
	wrong := binding
	wrong.Endpoint = "ssh://different.invalid"
	if _, e = x.Query(context.Background(), allocationID("x"), unitName(allocationID("x"), digest("x")), wrong); e == nil {
		t.Fatal("recovery destination drift allowed")
	}
}
