// Package sshprocess connects a prepared Linux facility using OpenSSH/SFTP.
// systemd owns execution lifetimes; NsJail owns task isolation. There is no
// Loom execution daemon and no per-task container or virtual machine.
package sshprocess

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/url"
	"os"
	"path"
	"regexp"
	"strings"
	"time"

	"github.com/pkg/sftp"
	"golang.org/x/crypto/ssh"
	"loom/runtime/contracts"
)

const Provider = "ssh-process/v1"

type Options struct {
	User                  string `json:"user"`
	HostKey               string `json:"host_key"`
	StateDirectory        string `json:"state_directory"`
	NsJail                string `json:"nsjail"`
	NsJailSHA256          string `json:"nsjail_sha256"`
	MemoryBytes           int64  `json:"memory_bytes"`
	Processes             int    `json:"processes"`
	CPUPercent            int    `json:"cpu_percent"`
	LeaseSeconds          int    `json:"lease_seconds"`
	RequestTimeoutSeconds int    `json:"request_timeout_seconds"`
}

type Client struct {
	binding contracts.Binding
	options Options
	key     string
	address string
	hostKey ssh.PublicKey
}

var namePattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]*$`)
var digestPattern = regexp.MustCompile(`^[a-f0-9]{64}$`)

func cleanPath(p string) bool {
	return path.IsAbs(p) && path.Clean(p) == p && p != "/" && !strings.ContainsAny(p, ":%$\n\r\x00")
}
func digest(s string) string { h := sha256.Sum256([]byte(s)); return hex.EncodeToString(h[:]) }
func quote(s string) string  { return "'" + strings.ReplaceAll(s, "'", "'\"'\"'") + "'" }
func argv(args ...string) string {
	q := make([]string, len(args))
	for i, s := range args {
		q[i] = quote(s)
	}
	return strings.Join(q, " ")
}

// Open validates only non-secret configuration. Setup can check the factory
// before provisioning a private key. Authentication happens at the first call.
func Open(binding contracts.Binding, key string) (contracts.TaskExecutor, error) {
	var o Options
	d := json.NewDecoder(strings.NewReader(binding.OptionsJSON))
	d.DisallowUnknownFields()
	if binding.Provider != Provider || binding.ServiceID == "" || !json.Valid([]byte(binding.OptionsJSON)) || d.Decode(&o) != nil {
		return nil, errors.New("invalid ssh-process/v1 binding")
	}
	u, e := url.Parse(binding.Endpoint)
	if e != nil || u.Scheme != "ssh" || u.User != nil || u.Hostname() == "" || u.Path != "" || u.RawQuery != "" || u.Fragment != "" {
		return nil, errors.New("SSH endpoint must be ssh://host[:port] without credentials or path")
	}
	port := u.Port()
	if port == "" {
		port = "22"
	}
	hostKey, _, _, rest, e := ssh.ParseAuthorizedKey([]byte(o.HostKey))
	if e != nil || len(strings.TrimSpace(string(rest))) != 0 || hostKey.Type() != ssh.KeyAlgoED25519 {
		return nil, errors.New("exactly one pinned Ed25519 SSH public host key required")
	}
	if o.User != "root" || !cleanPath(o.StateDirectory) || !cleanPath(o.NsJail) || !digestPattern.MatchString(o.NsJailSHA256) || o.MemoryBytes < 16777216 || o.Processes < 8 || o.CPUPercent < 1 || o.CPUPercent > 10000 || o.LeaseSeconds < 2 || o.LeaseSeconds > 86400 || o.RequestTimeoutSeconds < 1 || o.RequestTimeoutSeconds > 300 || key == "" {
		return nil, errors.New("explicit root management identity, private state, locked NsJail and positive resource/time limits required")
	}
	for _, public := range []string{"/usr", "/bin", "/lib", "/lib64"} {
		if o.StateDirectory == public || strings.HasPrefix(o.StateDirectory, public+"/") {
			return nil, errors.New("provider control state cannot be inside the public toolchain")
		}
	}
	return &Client{binding: binding, options: o, key: key, address: net.JoinHostPort(u.Hostname(), port), hostKey: hostKey}, nil
}
func (c *Client) Binding() contracts.Binding { return c.binding }

type connection struct {
	ssh   *ssh.Client
	files *sftp.Client
	stop  func() bool
}

func (c *Client) connect(ctx context.Context) (*connection, error) {
	signer, e := ssh.ParsePrivateKey([]byte(c.key))
	if e != nil {
		return nil, errors.New("SSH credential must be an unencrypted private key")
	}
	timeout := time.Duration(c.options.RequestTimeoutSeconds) * time.Second
	n, e := (&net.Dialer{Timeout: timeout}).DialContext(ctx, "tcp", c.address)
	if e != nil {
		return nil, e
	}
	stop := context.AfterFunc(ctx, func() { n.Close() })
	n.SetDeadline(time.Now().Add(timeout))
	s, ch, r, e := ssh.NewClientConn(n, c.address, &ssh.ClientConfig{User: c.options.User, Auth: []ssh.AuthMethod{ssh.PublicKeys(signer)}, HostKeyCallback: ssh.FixedHostKey(c.hostKey), HostKeyAlgorithms: []string{c.hostKey.Type()}})
	if e != nil {
		stop()
		n.Close()
		return nil, e
	}
	n.SetDeadline(time.Time{})
	x := &connection{ssh: ssh.NewClient(s, ch, r), stop: stop}
	x.files, e = sftp.NewClient(x.ssh)
	if e != nil {
		x.close()
		return nil, e
	}
	return x, nil
}
func (x *connection) close() {
	x.stop()
	if x.files != nil {
		x.files.Close()
	}
	x.ssh.Close()
}
func (x *connection) run(script string) (string, error) {
	s, e := x.ssh.NewSession()
	if e != nil {
		return "", e
	}
	defer s.Close()
	b, e := s.CombinedOutput("/bin/bash --noprofile --norc -euc " + quote(script))
	if e != nil {
		return string(b), fmt.Errorf("SSH management command: %w: %s", e, b)
	}
	return string(b), nil
}
func (x *connection) put(p string, r io.Reader, mode os.FileMode) error {
	f, e := x.files.OpenFile(p, os.O_WRONLY|os.O_CREATE|os.O_EXCL)
	if e != nil {
		return e
	}
	if e = f.Chmod(mode); e != nil {
		f.Close()
		return e
	}
	_, copyErr := io.Copy(f, r)
	return errors.Join(copyErr, f.Sync(), f.Close())
}
func (x *connection) read(p string, limit int64) ([]byte, error) {
	f, e := x.files.Open(p)
	if e != nil {
		return nil, e
	}
	defer f.Close()
	b, e := io.ReadAll(io.LimitReader(f, limit+1))
	if int64(len(b)) > limit {
		return nil, errors.New("remote evidence exceeds retention limit; complete result unknown")
	}
	return b, e
}

func (c *Client) withConnection(ctx context.Context, f func(*connection) error) error {
	ctx, cancel := context.WithTimeout(ctx, time.Duration(c.options.RequestTimeoutSeconds)*time.Second)
	defer cancel()
	x, e := c.connect(ctx)
	if e != nil {
		return e
	}
	defer x.close()
	return f(x)
}
