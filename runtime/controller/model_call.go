package controller

import (
	"context"
	"errors"
	"loom/runtime/model"
	"loom/runtime/rpc"
	"strconv"
	"time"
)

// Custody happens here, not in an externally supplied loop. A callback response
// can only become visible to the driver after the model outcome is durable.
func (c *run) invokeModel(ctx context.Context, p Object) (Object, error) {
	selected, err := c.runtime.bindModel(object(p["model"]))
	if err != nil {
		return nil, err
	}
	ms, err := number(p["timeoutMs"])
	limit, _ := number(c.basePlan["timeout"])
	if err != nil || ms <= 0 || ms > limit*1000 {
		return nil, errors.New("invalid model call timeout")
	}
	options := copyObject(object(p["options"]))
	options["maxRetries"] = 0
	options["timeoutMs"] = ms
	recordedModel := copyObject(selected)
	delete(recordedModel, "headers")
	event := Object{"type": "model_request", "model": recordedModel, "context": p["context"], "options": options}
	if err = c.event(event); err != nil {
		return nil, err
	}
	result, err := model.Invoke(ctx, c.runtime.ModelCommand, model.Request{
		Session: rpc.Session{RecordDirectory: c.work.ArtifactsDir(), WorkID: c.work.ID, RoundID: c.round.ID, Epoch: strconv.FormatInt(c.round.Epoch, 10), HarnessRef: c.round.HarnessRef},
		Model:   selected, Context: object(p["context"]), Options: options, APIKey: c.runtime.APIKey, Timeout: time.Duration(ms * float64(time.Millisecond))})
	if err != nil {
		return nil, err
	}
	if result["role"] != "assistant" {
		return nil, errors.New("model did not return an assistant message")
	}
	if err = c.event(Object{"type": "message_end", "message": result}); err != nil {
		return nil, err
	}
	return result, nil
}
