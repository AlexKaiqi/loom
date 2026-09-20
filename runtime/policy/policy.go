// Package policy speaks the external Harness ABI. Prompts and continuation
// strategy live in the Harness, never in the control Runtime.
package policy

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/santhosh-tekuri/jsonschema/v6"
	"loom/runtime/rpc"
)

type Object = map[string]any
type Tool struct {
	Name        string `json:"name"`
	Capability  string `json:"capability"`
	Description string `json:"description"`
	Parameters  Object `json:"parameters"`
	schema      *jsonschema.Schema
}
type Manifest struct {
	Protocol int               `json:"protocol"`
	Events   map[string]Object `json:"events"`
	Tools    []Tool            `json:"tools"`
}
type Client struct {
	Manifest Manifest
	rpc      *rpc.Client
	events   map[string]*jsonschema.Schema
}
type noExternalSchemas struct{}

func (noExternalSchemas) Load(string) (any, error) {
	return nil, errors.New("external schema references are not allowed")
}
func compile(value Object) (*jsonschema.Schema, error) {
	c := jsonschema.NewCompiler()
	c.UseLoader(noExternalSchemas{})
	if err := c.AddResource("urn:loom:schema", value); err != nil {
		return nil, err
	}
	return c.Compile("urn:loom:schema")
}
func Open(ctx context.Context, directory string, argv []string, launch func([]string) ([]string, error), session rpc.Session, handler rpc.Handler) (*Client, error) {
	directory, err := filepath.Abs(directory)
	if err != nil {
		return nil, err
	}
	data, err := os.ReadFile(filepath.Join(directory, "manifest.json"))
	if err != nil {
		return nil, errors.New("cannot read fixed Harness manifest")
	}
	c := &Client{events: map[string]*jsonschema.Schema{}}
	if err = rpc.Decode(data, &c.Manifest); err != nil {
		return nil, errors.New("invalid Harness manifest")
	}
	if c.Manifest.Protocol != 1 {
		return nil, errors.New("unsupported policy protocol")
	}
	names := map[string]bool{}
	for i := range c.Manifest.Tools {
		tool := &c.Manifest.Tools[i]
		if names[tool.Name] || tool.Name == "" || tool.Capability != "tool.exec" {
			return nil, errors.New("duplicate tool or unsupported capability")
		}
		names[tool.Name] = true
		tool.schema, err = compile(tool.Parameters)
		if err != nil {
			return nil, errors.New("invalid tool schema")
		}
	}
	for name, value := range c.Manifest.Events {
		c.events[name], err = compile(value)
		if err != nil {
			return nil, errors.New("invalid event schema")
		}
	}
	if launch == nil {
		return nil, errors.New("Harness requires a restricted Work execution domain")
	}
	command, err := rpc.Command(argv, "/harness")
	if err != nil {
		return nil, err
	}
	command, err = launch(command)
	if err != nil {
		return nil, err
	}
	c.rpc, err = rpc.Start(ctx, command, "", handler, "harness", session)
	if err != nil {
		return nil, err
	}
	return c, nil
}
func (c *Client) Close() { c.rpc.Close() }
func (c *Client) Call(ctx context.Context, method string, params any, result any) error {
	ctx, cancel := context.WithTimeout(ctx, 60*time.Second)
	defer cancel()
	return c.rpc.Call(ctx, method, params, result)
}
func (c *Client) Admit(ctx context.Context, kind string, payload Object, source string) error {
	if strings.HasPrefix(kind, "system.") {
		return errors.New("system facts cannot be submitted by an application")
	}
	schema, ok := c.events[kind]
	if !ok {
		return errors.New("event not declared by fixed Harness")
	}
	if err := schema.Validate(payload); err != nil {
		return errors.New("event payload does not satisfy declared schema")
	}
	var answer bool
	if err := c.Call(ctx, "policy.admit", Object{"kind": kind, "payload": payload, "source": source}, &answer); err != nil {
		return err
	}
	if !answer {
		return errors.New("Harness rejected event")
	}
	return nil
}
func (c *Client) ValidateTool(name string, args Object) error {
	for _, tool := range c.Manifest.Tools {
		if tool.Name == name {
			if err := tool.schema.Validate(args); err != nil {
				return errors.New("tool arguments do not satisfy declared schema")
			}
			return nil
		}
	}
	return errors.New("unregistered tool")
}
func (c *Client) NativeTools() []Object {
	out := []Object{}
	for _, t := range c.Manifest.Tools {
		out = append(out, Object{"name": t.Name, "description": t.Description, "parameters": t.Parameters})
	}
	return out
}
