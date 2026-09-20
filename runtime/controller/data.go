package controller

import (
	"encoding/json"
	"errors"
	"loom/runtime/rpc"
	"loom/runtime/work"
	"os"
	"path/filepath"
	"unicode/utf8"
)

func object(v any) Object { o, _ := v.(map[string]any); return o }
func copyObject(v Object) Object {
	out := Object{}
	for key, value := range v {
		out[key] = value
	}
	return out
}
func number(v any) (float64, error) {
	switch n := v.(type) {
	case json.Number:
		return n.Float64()
	case float64:
		return n, nil
	case int64:
		return float64(n), nil
	case int:
		return float64(n), nil
	}
	return 0, errors.New("number required")
}
func artifact(w *work.Work, value any) (Object, error) {
	data, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	return w.Artifact(data, ".json")
}
func asObject(value any) (Object, error) {
	data, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	var out Object
	err = rpc.Decode(data, &out)
	return out, err
}
func surface(w *work.Work) (Object, error) {
	files, err := work.Files(w.Surface)
	if err != nil {
		return nil, err
	}
	visible := Object{}
	for name, sha := range files {
		path := filepath.Join(w.Surface, name)
		info, err := os.Lstat(path)
		if err != nil {
			return nil, err
		}
		visible[name] = Object{"sha256": sha, "size": info.Size()}
		if info.Mode().IsRegular() {
			content, err := os.ReadFile(path)
			if err != nil {
				return nil, err
			}
			if utf8.Valid(content) {
				visible[name] = string(content)
			}
		}
	}
	return visible, nil
}
