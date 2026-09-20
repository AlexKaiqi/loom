//go:build darwin

package filesystem

import "golang.org/x/sys/unix"

func exchangeDirectories(a, b string) error {
	return unix.RenameatxNp(unix.AT_FDCWD, a, unix.AT_FDCWD, b, unix.RENAME_SWAP)
}
