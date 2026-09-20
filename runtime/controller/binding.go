package controller

import (
	"bytes"
	"encoding/json"
	"errors"
)

// A checkpoint contains the previous actual transport for audit, but a new
// dispatch resolves transport afresh. Policy may change context/options; model
// semantics are explicit Work requirements, never undeclared host defaults.
func (r *Runtime) bindModel(selected Object) (Object, error) {
	if selected != nil {
		expected, err := json.Marshal(modelSemantics(r.Model))
		if err != nil {
			return nil, err
		}
		actual, err := json.Marshal(modelSemantics(selected))
		if err != nil {
			return nil, err
		}
		if !bytes.Equal(expected, actual) {
			return nil, errors.New("policy model differs from the Work's declared model requirements")
		}
	}
	return copyObject(r.Model), nil
}

func modelSemantics(native Object) Object {
	out := copyObject(native)
	delete(out, "baseUrl")
	delete(out, "headers")
	return out
}
