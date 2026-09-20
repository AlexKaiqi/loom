package controller

import (
	"context"
	"errors"
	"loom/runtime/execution"
	"loom/runtime/model"
	"loom/runtime/policy"
	"loom/runtime/rpc"
	"loom/runtime/store"
	"loom/runtime/work"
	"math"
	"path/filepath"
	"strconv"
	"sync"
	"time"
)

type run struct {
	api                   harnessAPIState
	domain                *workDomain
	runtime               *Runtime
	work                  *work.Work
	policy                *policy.Client
	round                 store.Round
	mu                    sync.Mutex
	modelEffect           *store.Effect
	turnNumber            int
	lastTurn, lastRequest Object
	projectionRef         Object
	projectedContext      Object
	projectionPlan        Object
	basePlan              Object
	repairMode            bool
	repairAttempts        int
	continueDecision      *bool
	budgetEstimate        int
	budgetRef             Object
}

func (r *Runtime) Run(ctx context.Context, w *work.Work, resume bool) (result Object, err error) {
	local := *r
	r = &local // Deployment resolution belongs to this advance, never another Work.
	if err = r.Authority.Authorize(w); err != nil {
		return nil, err
	}
	if err = r.fenceOldDomains(w); err != nil {
		return nil, err
	}
	owner, err := store.ID()
	if err != nil {
		return nil, err
	}
	round, err := r.Authority.Claim(w, owner, resume)
	if err != nil {
		return nil, err
	}
	bound := *w
	bound.Control = w.Control.Bind(round)
	bound.Events = &store.Events{Path: w.Events.Path, Control: bound.Control}
	w = &bound
	current := &run{runtime: r, work: w, round: round}
	effects, err := w.Control.Effects(round.ID)
	initialCount := len(effects)
	settled := false
	defer func() {
		if settled || err == nil {
			return
		}
		if current.modelEffect != nil {
			_ = w.Control.UnknownEffect(current.modelEffect.ID, "model transport stopped without durable terminal result")
		}
		after, readErr := w.Control.Effects(round.ID)
		if resume && readErr == nil && len(after) == initialCount {
			_ = w.Control.ReturnReady(round.ID, "local continuation failure before a new dispatch")
			return
		}
		rejected, rejectErr := w.Control.RejectIfUndispatched(round.ID)
		if rejectErr != nil || !rejected {
			_ = w.Control.PauseRound(round.ID, "Round stopped; inspect durable effects before any continuation", nil)
		} else if errors.Is(err, rpc.ErrTransport) {
			// Only a durable rejection proves no model/tool dispatch occurred.
			// Never echo worker error payloads, which may contain credentials.
			err = errors.New("worker failed before model/tool dispatch; input remains pending. Check Harness configuration and limits")
		}
	}()
	if err != nil {
		return nil, err
	}
	// Claim fixed the strategy revision. Resolve deployment only from that
	// revision, including when a newer candidate was selected during a pause.
	w, err = w.ForStrategy(round.HarnessRef)
	if err != nil {
		return nil, err
	}
	current.work = w
	if r.Configure != nil {
		if err = r.Configure(r, w); err != nil {
			return nil, err
		}
	}
	domain, err := r.executionDomain(w, round, "harness")
	if err != nil {
		return nil, err
	}
	defer func() { err = errors.Join(err, domain.close()) }()
	// Materialize before the policy loader reads the manifest. The same immutable
	// directory is subsequently mounted read only by the launcher.
	if _, err = domain.harnessCommand(w, round, []string{"/bin/true"}); err != nil {
		return nil, err
	}
	selectedDefinition, err := work.ReadDefinition(filepath.Join(domain.snapshot, "work.toml"))
	if err != nil {
		return nil, err
	}
	requiredCapabilities := []string{}
	if len(w.Definition.Userspaces) > 0 {
		requiredCapabilities = append(requiredCapabilities, "userspace.binding/1")
	}
	current.domain = domain
	p, err := policy.Open(ctx, domain.strategyDirectory(), selectedDefinition.Harness.Argv, func(argv []string) ([]string, error) {
		mounts := []execution.Mount{{Source: filepath.Join(domain.binding.Staging, "outputs"), Destination: "/outputs", Writable: true}, {Source: filepath.Join(domain.snapshot, "harness"), Destination: "/harness"}, {Source: filepath.Join(domain.snapshot, "surface"), Destination: "/work/surface"}, {Source: filepath.Join(domain.binding.Staging, "facts"), Destination: "/facts"}, {Source: filepath.Join(domain.binding.Staging, "sources"), Destination: "/sources"}, {Source: filepath.Join(domain.binding.Staging, "resources"), Destination: "/resources"}}
		return domain.scope.Command(argv, mounts, "/harness", 3600)
	}, rpc.Session{LogDirectory: domain.binding.Staging, WorkID: w.ID, RoundID: round.ID, Epoch: strconv.FormatInt(round.Epoch, 10), HarnessRef: round.HarnessRef, Operations: harnessOperations, Capabilities: []string{"context.feedback/1", "userspace.binding/1"}, RequiredCapabilities: requiredCapabilities}, current.harnessCall)
	if err != nil {
		return nil, err
	}
	defer p.Close()
	current.policy = p
	current.domain = domain
	for _, effect := range effects {
		if effect.Kind == "model" {
			current.turnNumber++
		}
	}
	var plan Object
	if resume && round.Checkpoint != nil {
		var accepted Object
		err = current.policy.Call(ctx, "policy.resume", Object{"checkpoint_id": round.Checkpoint["checkpoint_id"]}, &accepted)
		current.api.advanceMu.Lock()
		plan = current.api.advancePlan
		current.api.advanceMu.Unlock()
		current.projectionRef = object(round.Checkpoint["projection_ref"])
		current.lastTurn = object(round.Checkpoint["native_turn"])
		priorPlan := object(round.Checkpoint["plan"])
		current.budgetRef = object(priorPlan["budget_feedback_ref"])
		if estimate, e := number(priorPlan["budget_estimate"]); e == nil {
			current.budgetEstimate = int(estimate)
		}
	} else {
		plan, err = current.projection(ctx, "policy.start", nil)
	}
	if err != nil {
		return nil, err
	}
	if current.handoffRequested() {
		result, err = current.finish(ctx)
		settled = err == nil
		return result, err
	}
	if plan == nil {
		return nil, errors.New("policy did not supply a plan")
	}
	current.repairMode = plan["execution_mode"] == "context_repair"
	current.projectedContext = object(plan["context"])
	if current.projectionPlan == nil {
		current.projectionPlan = copyObject(plan)
	}
	if count, e := number(plan["repair_attempts"]); e == nil {
		current.repairAttempts = int(count)
	}
	if err = current.validateSavedViews(plan); err != nil {
		return nil, err
	}
	if r.ActivateModel != nil {
		if err = r.ActivateModel(r); err != nil {
			return nil, err
		}
	}
	selected, err := r.bindModel(object(plan["model"]))
	if err != nil {
		return nil, err
	}

	seconds, err := number(plan["timeout"])
	if err != nil || seconds <= 0 || seconds > float64((1<<63-1)/int64(time.Second)-1) || math.IsNaN(seconds) || math.IsInf(seconds, 0) {
		return nil, errors.New("policy timeout must be positive and fit a duration")
	}
	maxTurns, err := number(plan["max_turns"])
	if err != nil || maxTurns < 1 || math.IsNaN(maxTurns) || math.IsInf(maxTurns, 0) || maxTurns != float64(int(maxTurns)) {
		return nil, errors.New("policy max_turns must be a positive integer")
	}
	options := object(plan["options"])
	if options == nil {
		options = Object{}
	}
	if _, present := options["maxTokens"]; !present {
		options["maxTokens"] = r.Model["maxTokens"]
	}
	preparedContext, err := current.withBudget(object(plan["context"]), options)
	if err != nil {
		return nil, err
	}
	current.basePlan = plan
	if current.projectionPlan == nil {
		current.projectionPlan = plan
	}
	messages, err := model.Run(ctx, r.ModelCommand, model.Request{Session: rpc.Session{RecordDirectory: w.ArtifactsDir(), WorkID: w.ID, RoundID: round.ID, Epoch: strconv.FormatInt(round.Epoch, 10), HarnessRef: round.HarnessRef, Operations: []string{"agent.event", "tool.execute", "agent.shouldStop", "agent.prepareTurn"}}, Context: preparedContext, Model: selected, Options: options, APIKey: r.APIKey, Tools: p.NativeTools(), MaxTurns: int(maxTurns), Timeout: time.Duration(seconds * float64(time.Second))}, model.Callbacks{Event: current.event, Tool: current.tool, Continue: current.continueTurn, Prepare: current.prepareTurn})
	if err != nil {
		return nil, err
	}
	if current.modelEffect != nil {
		return nil, store.ErrUnknownEffect
	}
	reference, err := artifact(w, messages)
	if err != nil {
		return nil, err
	}
	var assistant Object
	for _, m := range messages {
		if m["role"] == "assistant" {
			assistant = m
		}
	}
	if assistant == nil {
		return nil, errors.New("model returned no assistant result")
	}
	switch assistant["stopReason"] {
	case "error", "aborted", "length", "pending", "deferred":
		return nil, errors.New("model did not provide a complete result; retained for inspection")
	}
	if current.lastTurn != nil {
		more, err := current.finalContinuation(ctx)
		if err != nil {
			return nil, err
		}
		if more {
			update, err := current.prepareTurn(ctx, current.lastTurn)
			if err != nil {
				return nil, err
			}
			next := copyObject(plan)
			current.copyProjectionMetadata(next)
			next["repair_attempts"] = current.repairAttempts
			next["context"] = current.lastTurn["context"]
			next["model"] = current.lastRequest["model"]
			next["options"] = copyObject(object(current.lastRequest["options"]))
			for _, key := range []string{"context", "model"} {
				if value, ok := update[key]; ok {
					next[key] = value
				}
			}
			// Feedback is reconstructed and separately accounted at dispatch. Do
			// not persist it as part of the next raw Harness projection twice.
			next["context"] = current.projectedContext
			// Host transport headers may be reattached for immediate Pi dispatch,
			// but never enter the durable continuation checkpoint.
			if native := object(next["model"]); native != nil {
				saved := copyObject(native)
				delete(saved, "headers")
				next["model"] = saved
			}
			if thinking, ok := update["thinkingLevel"]; ok {
				options := object(next["options"])
				if thinking == "off" {
					delete(options, "reasoning")
				} else {
					options["reasoning"] = thinking
				}
			}
			if err = current.releaseAllocations(ctx); err != nil {
				return nil, err
			}
			if err = w.Control.PauseRound(round.ID, "confirmed model turn budget boundary", Object{"plan": next, "projection_ref": current.projectionRef, "content_ref": update["content_version"]}); err != nil {
				return nil, err
			}
			settled = true
			return nil, errors.New("policy requires continuation; explicit resume is available")
		}
	}
	result, err = current.finish(ctx)
	if err != nil {
		return nil, err
	}
	result["messages"] = reference
	settled = true
	return result, nil
}

func (c *run) copyProjectionMetadata(destination Object) {
	for _, key := range []string{"content_version", "harness_ref", "view_id", "fact_watermark", "resource_views", "sources", "selection", "template_sha256", "safe_boundaries", "protected_fact_ids", "execution_mode", "diagnostic", "previous_projection_ref", "budget_feedback_ref", "budget_estimate"} {
		if value, ok := c.projectionPlan[key]; ok {
			destination[key] = value
		} else {
			delete(destination, key)
		}
	}
}
func (c *run) continueTurn(ctx context.Context, turn Object) (bool, error) {
	var answer bool
	params, err := c.policyTurn(turn)
	if err != nil {
		return false, err
	}
	err = c.policy.Call(ctx, "policy.continue", params, &answer)
	if c.handoffRequested() {
		answer = false
	}
	if err == nil {
		c.mu.Lock()
		c.continueDecision = &answer
		c.mu.Unlock()
	}
	return answer, err
}
func (c *run) finalContinuation(ctx context.Context) (bool, error) {
	c.mu.Lock()
	decision := c.continueDecision
	c.mu.Unlock()
	if decision != nil {
		return *decision, nil
	}
	return c.continueTurn(ctx, c.lastTurn)
}
func (c *run) prepareTurn(ctx context.Context, turn Object) (Object, error) {
	update, err := c.projection(ctx, "policy.prepare", turn)
	if err != nil {
		return nil, err
	}
	options := object(c.lastRequest["options"])
	update["context"], err = c.withBudget(object(update["context"]), options)
	if err != nil {
		return nil, err
	}
	if update["model"] != nil {
		update["model"], err = c.runtime.bindModel(object(update["model"]))
	}
	return update, err
}
