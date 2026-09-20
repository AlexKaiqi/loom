package rpc

import (
	"bufio"
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"sync/atomic"
	"unicode/utf8"
)

const HandshakeLimit = 64 << 10
const FrameLimit = 4 << 20

// JSONLines only supplies loom/1 framing. Correlation, concurrent dispatch and
// cancellation still belong to the existing JSON-RPC library.
type JSONLines struct{ Limit atomic.Int64 }

func (c *JSONLines) WriteObject(w io.Writer, obj any) error {
	data, err := json.Marshal(obj)
	if err != nil {
		return err
	}
	if int64(len(data)) > c.Limit.Load() {
		return errors.New("RPC frame exceeds negotiated limit")
	}
	_, err = w.Write(append(data, '\n'))
	return err
}
func (c *JSONLines) ReadObject(r *bufio.Reader, obj any) error {
	var data []byte
	for {
		part, err := r.ReadSlice('\n')
		if int64(len(data)+len(part)) > c.Limit.Load()+1 {
			return errors.New("RPC frame exceeds negotiated limit")
		}
		data = append(data, part...)
		if err == nil {
			break
		}
		if err != bufio.ErrBufferFull {
			return err
		}
	}
	data = bytes.TrimSuffix(data, []byte{'\n'})
	if !utf8.Valid(data) || len(data) == 0 || data[0] != '{' {
		return errors.New("RPC requires one UTF-8 object per line; batches are unsupported")
	}
	return Decode(data, obj)
}
