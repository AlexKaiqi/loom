//go:build darwin || linux

package authority

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"syscall"
)

type Identity struct {
	Path   string `json:"path"`
	Device uint64 `json:"device"`
	Inode  uint64 `json:"inode"`
}

func StatIdentity(path string) (Identity, error) {
	var identity Identity
	path, err := filepath.EvalSymlinks(path)
	if err != nil {
		return identity, err
	}
	path, err = filepath.Abs(path)
	if err != nil {
		return identity, err
	}
	info, err := os.Stat(path)
	if err != nil {
		return identity, err
	}
	if !info.IsDir() {
		return identity, errors.New("authority target must be a directory")
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok {
		return identity, errors.New("Unix physical identity unavailable")
	}
	return Identity{Path: path, Device: uint64(stat.Dev), Inode: uint64(stat.Ino)}, nil
}
func contains(root, target string) bool {
	relative, err := filepath.Rel(root, target)
	return err == nil && (relative == "." || (relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator))))
}
func Overlaps(left, right string) bool { return contains(left, right) || contains(right, left) }
func (i Identity) samePhysical(other Identity) bool {
	return i.Device == other.Device && i.Inode == other.Inode
}
