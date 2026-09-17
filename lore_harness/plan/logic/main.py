"""Plan-mode action parsing and derived completion."""
import lore_harness_base as base


def parse(text):
    action = base.parse_action(text)
    if action.get("type") == "emit":
        if "kind" not in action or not isinstance(action.get("payload", {}), dict):
            return base.final_fallback(text)
    if action.get("type") == "shell" and not isinstance(action.get("script"), str):
        return base.final_fallback(text)
    return action


def settle(state):
    """Derive plan.completed once every declared stage has a completion fact."""
    facts = state.get("facts", [])
    folded = base.fold(facts, latest=("plan.created", "plan.revised"),
                       collect=("plan.stage.completed",), flags=("plan.completed",))
    spec = folded["plan.created"] or folded["plan.revised"]
    done = folded["plan.completed"]
    completed = [p.get("stage_id") for p in folded["plan.stage.completed"]]
    if done or not spec:
        return []
    stage_ids = [s.get("id") for s in spec.get("stages", [])]
    if stage_ids and all(stage_id in completed for stage_id in stage_ids):
        return [{"kind": "plan.completed", "payload": {"plan_id": spec.get("plan_id"), "stages": completed}}]
    return []
