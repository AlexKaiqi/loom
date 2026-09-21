package contracts_test

import (
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

// A second provider must not require editing configuration or Runtime. Inspect
// real production imports, including future subpackages, to guard that seam.
func TestProviderDependenciesPointTowardContracts(t *testing.T) {
	err := filepath.WalkDir("..", func(path string, entry os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() || !strings.HasSuffix(path, ".go") || strings.HasSuffix(path, "_test.go") {
			return nil
		}
		file, err := parser.ParseFile(token.NewFileSet(), path, nil, parser.ImportsOnly)
		if err != nil {
			return err
		}
		adapter := strings.HasPrefix(path, filepath.Join("..", "adapters")+string(os.PathSeparator))
		composition := strings.HasPrefix(path, filepath.Join("..", "cmd")+string(os.PathSeparator))
		for _, spec := range file.Imports {
			dependency, err := strconv.Unquote(spec.Path.Value)
			if err != nil {
				return err
			}
			if strings.HasPrefix(dependency, "loom/runtime/adapters/") && !composition {
				t.Errorf("%s imports concrete adapter %s", path, dependency)
			}
			if strings.Contains(dependency, "github.com/alibaba/OpenSandbox") && !adapter {
				t.Errorf("%s imports vendor SDK outside adapter", path)
			}
			if adapter && (dependency == "loom/runtime/config" || dependency == "loom/runtime/controller") {
				t.Errorf("%s reverses dependency on %s", path, dependency)
			}
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
}
