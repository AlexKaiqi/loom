package main

import (
	"fmt"
	"github.com/spf13/cobra"
	"loom/runtime/authority"
	"loom/runtime/controller"
	"loom/runtime/store"
	"loom/runtime/work"
	"time"
)

func eventCommands(root *cobra.Command, authorityPath, configPath *string) {
	var kinds []string
	var after int64
	subscribe := &cobra.Command{Use: "subscribe TARGET SOURCE KEY", Args: cobra.ExactArgs(3), RunE: func(cmd *cobra.Command, args []string) error {
		a, err := authority.Open(*authorityPath)
		if err != nil {
			return err
		}
		target, err := work.Open(args[0])
		if err != nil {
			return err
		}
		source, err := work.Open(args[1])
		if err != nil {
			return err
		}
		if err = a.RelayAllowed(source, target); err != nil {
			return err
		}
		if err = target.Events.Subscribe(args[2], source.ID, kinds, after); err != nil {
			return err
		}
		return (&controller.Runtime{Authority: a}).PumpSubscriptions(target, map[string]*work.Work{source.ID: source})
	}}
	subscribe.Flags().StringSliceVar(&kinds, "kind", nil, "event kinds (required)")
	_ = subscribe.MarkFlagRequired("kind")
	subscribe.Flags().Int64Var(&after, "after", 0, "saved source sequence to start after; includes already recorded events")
	root.AddCommand(subscribe)
	var concurrency int
	var interval time.Duration
	serve := &cobra.Command{Use: "serve", Args: cobra.NoArgs, RunE: func(cmd *cobra.Command, _ []string) error {
		a, err := authority.Open(*authorityPath)
		if err != nil {
			return err
		}
		return (controller.Scheduler{Authority: a, Interval: interval, Concurrency: concurrency, RuntimeFor: func(w *work.Work) (*controller.Runtime, error) {
			r := &controller.Runtime{Authority: a}
			err := bindRuntime(r, w, *configPath)
			return r, err
		}, Observe: func(id string, err error) {
			if err != nil {
				fmt.Fprintf(cmd.ErrOrStderr(), "Work %s: %v\n", id, err)
			}
		}}).Serve(cmd.Context())
	}}
	serve.Flags().IntVar(&concurrency, "concurrency", 4, "maximum active Work advances")
	serve.Flags().DurationVar(&interval, "scan-interval", time.Second, "persistent responsibility scan interval")
	root.AddCommand(serve)
	view := &cobra.Command{Use: "facts-view PATH", Args: cobra.ExactArgs(1), RunE: func(cmd *cobra.Command, args []string) error {
		a, err := authority.Open(*authorityPath)
		if err != nil {
			return err
		}
		w, err := work.Open(args[0])
		if err != nil {
			return err
		}
		if err = a.Authorize(w); err != nil {
			return err
		}
		v, err := w.Events.OpenView(store.ViewScope{WorkID: w.ID}, 0)
		if err != nil {
			return err
		}
		fmt.Fprintln(cmd.OutOrStdout(), v.Database)
		return nil
	}}
	root.AddCommand(view)
}
