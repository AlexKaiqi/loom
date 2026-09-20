package controller

import (
	"context"
	"errors"
	"fmt"
	"slices"
	"sync"
	"time"

	"loom/runtime/authority"
	"loom/runtime/store"
	"loom/runtime/work"
)

// PumpSubscriptions is a recoverable scan, not a notification consumer. Each
// delivery first atomically creates its target input under the original source
// identity, then advances that subscription's cursor. No cross-DB transaction
// or live Harness is required, including for events predating the subscription.
func (r *Runtime) PumpSubscriptions(target *work.Work, sources map[string]*work.Work) error {
	if err := r.Authority.Authorize(target); err != nil {
		return err
	}
	subscriptions, err := target.Events.Subscriptions()
	if err != nil {
		return err
	}
	for _, sub := range subscriptions {
		if !sub.Active {
			continue
		}
		source := sources[sub.SourceWorkID]
		if source == nil {
			return fmt.Errorf("dependency_missing: source Work %s", sub.SourceWorkID)
		}
		if err = r.Authority.RelayAllowed(source, target); err != nil {
			return err
		}
		facts, err := source.Events.Events(sub.Cursor)
		if err != nil {
			return err
		}
		for _, fact := range facts {
			var input int64
			if slices.Contains(sub.Kinds, fact.Kind) {
				// Recheck current authority before every new delivery; registration
				// and reading a source path do not grant continued relay rights.
				if err = r.Authority.RelayAllowed(source, target); err != nil {
					return err
				}
				received, err := target.Events.Admit("work:"+source.ID, "fact:"+fact.FactID, fact.Kind, fact.Payload)
				if err != nil {
					return err
				}
				input = received.Seq
			}
			if err = target.Events.ConfirmDelivery(sub.ID, sub.Cursor, fact.Seq, fact.FactID, input); err != nil {
				return err
			}
			sub.Cursor = fact.Seq
		}
	}
	return nil
}

type Scheduler struct {
	Authority   *authority.Authority
	RuntimeFor  func(*work.Work) (*Runtime, error)
	Interval    time.Duration
	Concurrency int
	Observe     func(string, error)
}

func (s Scheduler) Serve(ctx context.Context) error {
	if s.Interval <= 0 || s.Concurrency < 1 || s.RuntimeFor == nil {
		return errors.New("scheduler requires a positive interval, concurrency and runtime resolver")
	}
	ticker := time.NewTicker(s.Interval)
	defer ticker.Stop()
	active := map[string]bool{}
	var mu sync.Mutex
	var wg sync.WaitGroup
	defer wg.Wait()
	observe := func(id string, err error) {
		if s.Observe != nil {
			s.Observe(id, err)
		}
	}
	for {
		works, err := s.Authority.Works(observe)
		if err != nil {
			return err
		}
		sources := map[string]*work.Work{}
		for _, w := range works {
			sources[w.ID] = w
		}
		for _, w := range works {
			if err = (&Runtime{Authority: s.Authority}).PumpSubscriptions(w, sources); err != nil {
				observe(w.ID, err)
				continue
			}
			pending, err := w.Events.Pending()
			if err != nil {
				observe(w.ID, err)
				continue
			}
			rounds, err := w.Control.Rounds()
			if err != nil {
				observe(w.ID, err)
				continue
			}
			ready, resume := true, false
			for _, round := range rounds {
				if round.State == "ready" {
					resume = true
				} else if round.State != "handed_off" {
					ready = false
					break
				}
			}
			if !ready || (!resume && len(pending) == 0) {
				continue
			}
			mu.Lock()
			if active[w.ID] || len(active) >= s.Concurrency {
				mu.Unlock()
				continue
			}
			active[w.ID] = true
			mu.Unlock()
			wg.Add(1)
			go func(w *work.Work, resume bool) {
				defer wg.Done()
				defer func() { mu.Lock(); delete(active, w.ID); mu.Unlock() }()
				r, err := s.RuntimeFor(w)
				if err == nil {
					_, err = r.Run(ctx, w, resume)
				}
				if !errors.Is(err, store.ErrConflict) {
					observe(w.ID, err)
				}
			}(w, resume)
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}
