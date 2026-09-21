package opensandbox

import (
	"crypto/sha256"
	"encoding/hex"
	"loom/runtime/adapters/internal/taskio"
)

func digestBytes(data []byte) string { h := sha256.Sum256(data); return hex.EncodeToString(h[:]) }

var save = taskio.Save
