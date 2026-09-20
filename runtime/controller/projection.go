package controller

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"loom/runtime/rpc"
	"loom/runtime/store"
	"path/filepath"
	"sort"
)

// projection delegates all content selection to Harness. The Runtime supplies a
// fixed, authorized fact boundary and preserves the result before model dispatch.
func (c *run) projection(ctx context.Context, method string, turn Object) (Object, error) {
	for alias := range c.work.Definition.Userspaces {
		if _, err := c.runtime.Authority.Resource(c.work, alias); err != nil {
			return nil, err
		}
	}
	// Capture source bytes before asking Harness to render them. It sees a fixed
	// readonly filesystem view, so facts do not need to fit inside one RPC frame.
	var version string
	err := c.work.Control.Owned(func() error { var e error; version, e = c.work.Snapshot("projection sources"); return e })
	if err != nil {
		return nil, err
	}
	snapshot := filepath.Join(c.domain.binding.Staging, "sources", version)
	if err = c.work.Materialize(version, snapshot); err != nil {
		return nil, err
	}
	if err = rolePermissions(snapshot, c.domain.scope.UID, false); err != nil {
		return nil, err
	}
	all, err := c.work.Events.Events(0)
	if err != nil {
		return nil, err
	}
	claimed, err := c.work.Control.ClaimedInputs(c.round.ID)
	if err != nil {
		return nil, err
	}
	required := []string{}
	claimedSet := map[int64]bool{}
	for _, seq := range claimed {
		required = append(required, fmt.Sprintf("F%d", seq))
		claimedSet[seq] = true
	}
	pending, err := c.work.Events.Pending()
	if err != nil {
		return nil, err
	}
	excluded := map[int64]bool{}
	for _, fact := range pending {
		if !claimedSet[fact.Seq] {
			excluded[fact.Seq] = true
		}
	}
	ids := []string{}
	for _, fact := range all {
		if !excluded[fact.Seq] {
			ids = append(ids, fact.FactID)
		}
	}
	viewToken, err := store.ID()
	if err != nil {
		return nil, err
	}
	mountPath := "/facts/" + viewToken
	view, err := c.work.Events.OpenView(store.ViewScope{WorkID: c.work.ID, FactIDs: ids, MountPath: mountPath}, c.round.InputSeq)
	if err != nil {
		return nil, err
	}
	if err = accessibleCopy(view.Directory, filepath.Join(c.domain.binding.Staging, "facts", viewToken), c.domain.scope.UID, false); err != nil {
		return nil, err
	}
	if err = c.writeInterface(filepath.Join(c.domain.binding.Staging, "facts", viewToken), c.domain.scope.UID, c.domain.scope.GID); err != nil {
		return nil, err
	}
	c.api.mu.Lock()
	if c.api.views == nil {
		c.api.views = map[string]boundFactView{}
	}
	c.api.views[view.ID] = boundFactView{FactView: view, MountPath: mountPath}
	c.api.mu.Unlock()
	resources, _, err := c.resourceViews(c.domain)
	if err != nil {
		return nil, err
	}
	c.api.mu.Lock()
	c.api.basis = projectionBasis{ContentRef: version, ViewID: view.ID, Watermark: view.Watermark, Resources: resources}
	c.api.mu.Unlock()
	var result Object
	operation := ""
	if method == "policy.start" {
		operation = "model.start"
	}
	handoff, err := c.handoffBasis()
	if err != nil {
		return nil, err
	}
	params := Object{"handoff_basis": handoff, "output_directory": "/outputs", "repair_attempts": c.repairAttempts, "previous_projection_ref": c.projectionRef, "model_operation": operation, "content_version": version, "harness_ref": c.round.HarnessRef, "resource_views": resources, "files_root": "/sources/" + version, "facts_database": mountPath + "/facts.sqlite", "fact_watermark": view.Watermark, "view_id": view.ID, "required_fact_ids": required, "model_semantics": modelSemantics(c.runtime.Model), "timestamp": 0}
	params["interface_path"] = mountPath + "/interface.json"
	turnParams, err := c.policyTurn(turn)
	if err != nil {
		return nil, err
	}
	for k, v := range turnParams {
		params[k] = v
	}
	err = c.policy.Call(ctx, method, params, &result)
	if err != nil {
		return nil, err
	}
	if c.handoffRequested() {
		if method == "policy.start" {
			return nil, nil
		}
		return nil, errors.New("not_ready: handoff accepted during model advancement")
	}
	if diagnostic := object(result["projection_error"]); diagnostic != nil {
		ref, e := artifact(c.work, diagnostic)
		if e != nil {
			return nil, e
		}
		if _, e = c.work.Events.AppendOwned("runtime", "projection-rejected:"+view.ID, "projection.rejected", Object{"diagnostic_ref": ref, "content_version": version}); e != nil {
			return nil, e
		}
		return nil, &rpc.Error{Kind: "invalid_request", Diagnostic: fmt.Sprint(diagnostic["diagnostic"])}
	}
	if result == nil || result["projection_ref"] == nil {
		return nil, errors.New("Harness did not publish a projection")
	}
	encoded, e := json.Marshal(result["projection_ref"])
	if e != nil {
		return nil, e
	}
	var ref store.RecordRef
	if e = json.Unmarshal(encoded, &ref); e != nil {
		return nil, e
	}
	c.api.mu.Lock()
	published, ok := c.api.published[ref.SHA256]
	c.api.mu.Unlock()
	if !ok || published != ref {
		return nil, errors.New("permission_denied: projection was not published on this channel")
	}
	c.api.advanceMu.Lock()
	accepted := c.api.advancePlan != nil && c.api.advanceRef == ref
	c.api.advanceMu.Unlock()
	if method == "policy.start" && !accepted {
		return nil, errors.New("Harness did not request model.start for this projection")
	}
	raw, e := c.readPolicyRecord(ref)
	if e != nil {
		return nil, e
	}
	if e = json.Unmarshal(raw, &result); e != nil {
		return nil, e
	}
	reference, e := asObject(ref)
	if e != nil {
		return nil, e
	}
	c.projectionRef = reference
	c.projectedContext = object(result["context"])
	c.repairMode = result["execution_mode"] == "context_repair"
	if c.repairMode {
		if turn == nil {
			return nil, &rpc.Error{Kind: "not_ready", Diagnostic: "context repair budget exhausted"}
		}
		if err = c.validateSavedViews(c.projectionPlan); err != nil {
			return nil, err
		}
		c.repairAttempts++
	}
	c.projectionPlan = copyObject(result)
	return result, nil
}

// Budget feedback is an explicitly labelled conservative estimate, never the
// previous request's usage. Unknown capacity blocks instead of guessing. Content
// selection and any body folding have already happened in Harness.
func (c *run) withBudget(context Object, options Object) (Object, error) {
	window, err := number(c.runtime.Model["contextWindow"])
	if err != nil || window <= 0 {
		return nil, errors.New("not_ready: model context window unknown")
	}
	output, err := number(options["maxTokens"])
	if err != nil || output <= 0 {
		return nil, errors.New("not_ready: output reservation required")
	}
	if maximum, e := number(c.runtime.Model["maxTokens"]); e == nil && output > maximum {
		return nil, errors.New("requested output exceeds model capacity")
	}
	candidate := copyObject(context)
	candidate["tools"] = c.policy.NativeTools()
	raw, err := json.Marshal(candidate)
	if err != nil {
		return nil, err
	}
	// The bounded feedback envelope is reserved before serializing itself. UTF-8
	// bytes overestimate ordinary text tokens; unsupported binary blocks reject.
	for _, message := range arrayObjects(candidate["messages"]) {
		for _, block := range arrayObjects(message["content"]) {
			if block["type"] == "image" {
				return nil, errors.New("capability_missing: no verified image budget estimator")
			}
		}
	}
	estimate := len(raw) + 2048
	reserve := 4096
	pressure := "normal"
	if float64(estimate+reserve)+output > window {
		pressure = "high"
	}
	feedback := Object{"schema_version": 1, "capability": "context.feedback/1", "model_id": c.runtime.Model["id"], "projection_ref": c.projectionRef, "effective_window": window, "next_input_estimate": estimate, "estimate_method": "UTF-8 serialized bytes plus 2048 protocol/feedback allowance; text only, conservative estimate", "output_reserved": output, "editing_reserved": reserve, "pressure": pressure, "edit": "surface/main.md", "selection_status": "applied"}
	if c.repairMode {
		feedback["selection_status"] = "rejected; context repair only"
	}
	if c.lastTurn != nil {
		feedback["previous_usage"] = object(c.lastTurn["message"])["usage"]
	}
	details := copyObject(feedback)
	details["model_service"], details["model_semantics"] = c.work.Definition.Model.Service, modelSemantics(c.runtime.Model)
	details["harness_ref"], details["template_sha256"], details["content_version"] = c.round.HarnessRef, c.projectionPlan["template_sha256"], c.projectionPlan["content_version"]
	details["sources"], details["selection"], details["safe_boundaries"], details["protected_fact_ids"] = c.projectionPlan["sources"], c.projectionPlan["selection"], c.projectionPlan["safe_boundaries"], c.projectionPlan["protected_fact_ids"]
	details["diagnostic"] = c.projectionPlan["diagnostic"]
	details["threshold_source"] = "runtime text-budget/1: effective Work model window; output from Harness request; 4096 editing reserve; 2048 bounded feedback/protocol allowance"
	details["source_estimate_method"] = "Harness UTF-8 contribution estimates; provenance verified against fixed files/fact view; source groups exclude some message/protocol wrappers and are not provider token usage"
	details["previous_feedback_ref"] = c.budgetRef
	if c.budgetRef != nil {
		details["input_estimate_delta"] = estimate - c.budgetEstimate
	}
	systemBytes, _ := json.Marshal(candidate["systemPrompt"])
	toolBytes, _ := json.Marshal(candidate["tools"])
	messageBytes, _ := json.Marshal(candidate["messages"])
	details["serialized_components"] = Object{"system_utf8_bytes": len(systemBytes), "tools_utf8_bytes": len(toolBytes), "messages_utf8_bytes": len(messageBytes), "input_utf8_bytes": len(raw), "multimedia": "text only; unsupported media reject"}
	ref, err := artifact(c.work, details)
	if err != nil {
		return nil, err
	}
	fact, err := c.work.Events.AppendOwned("runtime", "context-feedback:"+c.round.ID+":"+fmt.Sprint(ref["sha256"]), "context.feedback", details)
	if err != nil {
		return nil, err
	}
	feedback["details_fact_id"], feedback["details_ref"] = fact.FactID, ref
	feedback["threshold_policy"] = "runtime text-budget/1"
	groups := append([]Object(nil), arrayObjects(c.projectionPlan["sources"])...)
	sort.SliceStable(groups, func(i, j int) bool {
		a, _ := number(groups[i]["utf8_bytes"])
		b, _ := number(groups[j]["utf8_bytes"])
		return a > b
	})
	major := []Object{}
	for _, source := range groups[:min(3, len(groups))] {
		item := Object{"kind": source["kind"], "bytes": source["utf8_bytes"], "protected": source["protected_reason"]}
		if path, ok := source["path"].(string); ok && len(path) < 160 {
			item["path"] = path
		}
		if ids, ok := source["fact_ids"].([]any); ok && len(ids) > 0 {
			item["first_fact"] = ids[0]
			item["safe_after"] = source["safe_after"]
		}
		major = append(major, item)
	}
	feedback["major_sources"] = major
	c.budgetRef, c.budgetEstimate = ref, estimate
	if c.projectionPlan != nil {
		c.projectionPlan["budget_feedback_ref"], c.projectionPlan["budget_estimate"] = ref, estimate
	}
	encoded, err := json.Marshal(feedback)
	if err != nil {
		return nil, err
	}
	for len(encoded) > 1536 && len(major) > 0 {
		major = major[:len(major)-1]
		feedback["major_sources"] = major
		encoded, err = json.Marshal(feedback)
		if err != nil {
			return nil, err
		}
	}
	if len(encoded) > 1536 {
		// The complete source/usage record remains readable through details_fact_id.
		delete(feedback, "previous_usage")
		encoded, err = json.Marshal(feedback)
		if err != nil {
			return nil, err
		}
		if len(encoded) > 1536 {
			return nil, errors.New("context feedback exceeds reserved envelope")
		}
	}
	prompt, _ := candidate["systemPrompt"].(string)
	candidate["systemPrompt"] = prompt + "\n[Runtime context feedback; estimates are not provider usage]\n" + string(encoded)
	if float64(estimate)+output > window {
		_, saveErr := artifact(c.work, Object{"context_feedback": feedback, "blocked": "context capacity exceeded"})
		return nil, errors.Join(errors.New("not_ready: required projection exceeds context capacity; edit surface/main.md"), saveErr)
	}
	return candidate, nil
}
func arrayObjects(value any) []Object {
	out := []Object{}
	switch items := value.(type) {
	case []Object:
		return items
	case []any:
		for _, item := range items {
			if m := object(item); m != nil {
				out = append(out, m)
			}
		}
	}
	return out
}
