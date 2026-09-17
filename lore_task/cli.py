"""Command line entry: create / admit / run / status / facts.

Credentials: `--env-file` (default `~/.env`) + `--api-key-env` (default
`ARC_PLAN_API_KEY`). The key is read into process memory only; it is never
written into the task directory or into evidence.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import layout, ledger, provider as provider_mod, round as round_mod

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
DEFAULT_MODEL = "glm-5.3-flash"
DEFAULT_MODEL_ALIAS = "glm-5-3-flash"
DEFAULT_ENV_FILE = "~/.env"
DEFAULT_API_KEY_ENV = "ARC_PLAN_API_KEY"


def _json_arg(text):
    return json.loads(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lore_task", description="Task-directory runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create a task directory from a harness template")
    create.add_argument("--root", required=True)
    create.add_argument("--task-id", required=True)
    create.add_argument("--harness", required=True)
    create.add_argument("--workspace", action="append", default=[],
                        help="authorized file range outside the task dir (repeatable; path)")

    admit = sub.add_parser("admit", help="admit an external fact through Fact Admission")
    admit.add_argument("--root", required=True)
    admit.add_argument("--task-id", required=True)
    admit.add_argument("--foreign-id", required=True)
    admit.add_argument("--kind", required=True)
    admit.add_argument("--payload", default="{}")

    run = sub.add_parser("run", help="run one Round if a trigger condition is met")
    run.add_argument("--root", required=True)
    run.add_argument("--task-id", required=True)
    run.add_argument("--provider", choices=("faux", "ark"), default="ark")
    run.add_argument("--faux-response", action="append", default=[])
    run.add_argument("--base-url", default=DEFAULT_BASE_URL)
    run.add_argument("--model", default=DEFAULT_MODEL)
    run.add_argument("--model-alias", default=DEFAULT_MODEL_ALIAS)
    run.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    run.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV)
    run.add_argument("--max-tokens", type=int, default=4096)
    run.add_argument("--max-steps", type=int, default=8)
    run.add_argument("--timeout", type=float, default=180.0)
    run.add_argument("--tool-check-interval", type=float, default=round_mod.TOOL_CHECK_INTERVAL,
                     help="seconds between sys.tool.check observations (never kills)")
    run.add_argument("--tool-budget", type=float, default=None,
                     help="default policy budget in ms for calls without budget_ms (ends the wait -> timeout)")
    run.add_argument("--tool-hard-cap", type=float, default=round_mod.TOOL_HARD_CAP,
                     help="runtime resource safety net in seconds (-> abandoned, unknown)")

    status = sub.add_parser("status", help="print task status")
    status.add_argument("--root", required=True)
    status.add_argument("--task-id", required=True)

    facts = sub.add_parser("facts", help="print the fact stream")
    facts.add_argument("--root", required=True)
    facts.add_argument("--task-id", required=True)

    recover = sub.add_parser("recover", help="quarantine facts beyond the commit point (interrupted Round)")
    recover.add_argument("--root", required=True)
    recover.add_argument("--task-id", required=True)
    recover.add_argument("--keep", type=int, default=None)

    relate = sub.add_parser("relate", help="declare cross-task wants/grants (PEER:KIND[,KIND])")
    relate.add_argument("--root", required=True)
    relate.add_argument("--task-id", required=True)
    relate.add_argument("--want", action="append", default=[])
    relate.add_argument("--grant", action="append", default=[])

    register = sub.add_parser("register", help="(re-)register an existing task in this root's host authority (import/adopt)")
    register.add_argument("--root", required=True)
    register.add_argument("--task-id", required=True)

    relay = sub.add_parser("relay", help="relay one event through another task's Fact Admission (authorized by wants+grants)")
    relay.add_argument("--from-root", required=True)
    relay.add_argument("--from-task", required=True)
    relay.add_argument("--to-root", required=True)
    relay.add_argument("--to-task", required=True)
    relay.add_argument("--foreign-id", required=True)
    relay.add_argument("--kind", required=True)
    relay.add_argument("--payload", default="{}")

    return parser


def _relation(text):
    peer, _, kinds = str(text).partition(":")
    if not peer or not kinds:
        raise SystemExit("relation must be PEER:KIND[,KIND]")
    return peer, [k for k in kinds.split(",") if k]


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "create":
        workspaces = []
        for raw in args.workspace:
            path = os.path.abspath(os.path.expanduser(raw))
            if not os.path.isdir(path):
                print(json.dumps({"error": f"workspace is not a directory: {path}"}), file=sys.stderr)
                return 2
            workspaces.append({"id": os.path.basename(path), "path": path, "mode": "rw"})
        base = layout.create_task(args.root, args.task_id, args.harness, workspaces=workspaces)
        print(json.dumps({"created": str(base), "task": layout.read_json(layout.paths(base)["task"])},
                         ensure_ascii=False, indent=2))
        return 0

    if args.command == "relay":
        result = round_mod.relay(
            layout.task_path(args.from_root, args.from_task),
            layout.task_path(args.to_root, args.to_task),
            args.foreign_id, args.kind, _json_arg(args.payload))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    base = layout.task_path(args.root, args.task_id)

    if args.command == "admit":
        result = round_mod.admit(base, args.foreign_id, args.kind, _json_arg(args.payload))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "register":
        entry = layout.register_authority(args.root, args.task_id, base)
        print(json.dumps({"registered": entry}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "status":
        print(json.dumps(round_mod.status(base), ensure_ascii=False, indent=2))
        return 0

    if args.command == "facts":
        for fact in __import__("lore_task.facts", fromlist=["read_facts"]).read_facts(base):
            print(json.dumps(fact, ensure_ascii=False, sort_keys=True))
        return 0

    if args.command == "recover":
        print(json.dumps(round_mod.recover(base, keep=args.keep), ensure_ascii=False, indent=2))
        return 0

    if args.command == "relate":
        result = {"task_id": args.task_id}
        for want in args.want:
            result = round_mod.relate(base, want=_relation(want))
        for grant in args.grant:
            result = round_mod.relate(base, grant=_relation(grant))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "run":
        if args.provider == "faux":
            client = provider_mod.FauxProvider(args.faux_response)
        else:
            env = provider_mod.load_env_file(args.env_file)
            key = env.get(args.api_key_env) or os.environ.get(args.api_key_env)
            if not key:
                print(json.dumps({"error": f"missing key: {args.api_key_env} in {args.env_file}"}), file=sys.stderr)
                return 2
            client = provider_mod.OpenAICompatProvider(
                args.base_url, key, args.model, alias=args.model_alias,
                timeout=args.timeout, max_tokens=args.max_tokens)
        result = round_mod.run_round(base, client, max_steps=args.max_steps,
                                     tool_check_interval=args.tool_check_interval,
                                     tool_budget=args.tool_budget,
                                     tool_hard_cap=args.tool_hard_cap)
        result["provider"] = client.name
        result["model"] = getattr(client, "model", None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
