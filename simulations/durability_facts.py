"""Independent finite fixture facts and durable records; no test oracle imports."""
from copy import deepcopy


def bounded_count(items):
    count = len(items)
    return count if count <= 2 else "overflow"


class ContentFacts:
    """Confirmation history, reference locators and stored bytes are distinct."""

    def __init__(self, confirmed, resolvable, locations=None, sandbox_only=False):
        self.confirmations = {}
        self.locators = {}
        self.blobs = {}
        self.authorized = {}
        self.durability = {}
        self.history = []
        locations = locations or {}
        for ref in confirmed:
            self.confirmations[ref] = ref
            self.authorized[ref] = True
            location = locations.get(ref, "hot")
            self.locators[ref] = location
            if ref in resolvable:
                self.blobs[(location, ref)] = ref
                self.durability[(location, ref)] = "sandbox" if sandbox_only else "durable"
            self.history.append({"event": "initial_confirmation", "ref": ref})
        # The initial fixture can expose readable content not yet confirmed.
        for ref in resolvable:
            if ref not in self.locators:
                self.locators[ref] = locations.get(ref, "hot")
                self.blobs[(self.locators[ref], ref)] = ref
                self.authorized[ref] = True
                self.durability[(self.locators[ref], ref)] = "durable"

    def confirm(self, ref, content=None, location="hot"):
        content = ref if content is None else deepcopy(content)
        if ref in self.confirmations and self.confirmations[ref] != content:
            raise ValueError("conflicting content identity")
        self.confirmations[ref] = deepcopy(content)
        self.locators[ref] = location
        self.blobs[(location, ref)] = deepcopy(content)
        self.authorized[ref] = True
        self.durability[(location, ref)] = "durable"
        self.history.append({"event": "confirmed", "ref": ref, "content": content})

    def resolve(self, ref):
        if not self.authorized.get(ref, False):
            return None
        location = self.locators.get(ref)
        value = self.blobs.get((location, ref))
        if ref in self.confirmations and value != self.confirmations[ref]:
            return None
        return deepcopy(value)

    def resolvable(self):
        return [ref for ref in self.confirmations if self.resolve(ref) is not None]

    def expire(self, ref):
        location = self.locators.get(ref)
        self.blobs.pop((location, ref), None)
        self.durability.pop((location, ref), None)
        self.history.append({"event": "expired", "ref": ref})

    def archive(self, ref, destination, stale_reference=False):
        old_location = self.locators.get(ref)
        value = self.resolve(ref)
        if value is None:
            raise ValueError("cannot archive inaccessible record")
        self.blobs[(destination, ref)] = value
        self.durability[(destination, ref)] = self.durability.pop((old_location, ref), "durable")
        if old_location != destination:
            self.blobs.pop((old_location, ref), None)
        if not stale_reference:
            self.locators[ref] = destination
        self.history.append({"event": "archived", "ref": ref, "destination": destination})

    def crash_sandbox(self):
        lost = [key for key, value in self.durability.items() if value == "sandbox"]
        for key in lost:
            self.blobs.pop(key, None)
            self.durability.pop(key, None)
        self.history.append({"event": "sandbox_lost", "lost": [list(k) for k in lost]})

    def evidence(self):
        return {"confirmations": deepcopy(self.confirmations), "locators": deepcopy(self.locators),
                "authorized": deepcopy(self.authorized),
                "physical_records": [{"location": k[0], "identity": k[1], "content": deepcopy(v),
                                      "durability": self.durability.get(k)} for k, v in self.blobs.items()],
                "history": deepcopy(self.history)}


class Responsibilities:
    def __init__(self, pending, required_refs):
        self.records = {}
        self.history = []
        for identity in pending:
            self.accept(identity, required_refs)

    def accept(self, identity, required_refs=(), event_refs=()):
        if identity not in self.records:
            self.records[identity] = {"required_refs": list(required_refs), "event_refs": list(event_refs),
                                      "status": "pending", "durable": True}
            self.history.append({"event": "accepted", "identity": identity})

    def retire(self, identity, reason):
        if identity in self.records:
            self.records[identity]["status"] = "retired"
            self.history.append({"event": "retired", "identity": identity, "reason": reason})

    def pending(self):
        return [key for key, value in self.records.items() if value["status"] == "pending"]

    def recoverable(self, content, events):
        available_events = {event["id"] for event in events}
        for record in self.records.values():
            if record["status"] != "pending" or not record["durable"]:
                continue
            if (all(content.resolve(ref) is not None for ref in record["required_refs"])
                    and all(ref in available_events for ref in record["event_refs"])):
                return True
        return False

    def lose_volatile(self):
        for identity, record in list(self.records.items()):
            if not record["durable"]:
                del self.records[identity]
                self.history.append({"event": "volatile_record_lost", "identity": identity})


class EnvironmentFacts:
    def __init__(self, initial):
        def seeded(count, kind):
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError("fixture counter must initialize to a finite nonnegative integer")
            return [{"origin": "initial_fixture", "identity": f"{kind}:{i}"} for i in range(count)]
        self.effects = seeded(initial["external_effect_count"], "effect")
        self.model_calls = seeded(initial["model_call_count"], "model")
        self.launches = seeded(initial["launch_count"], "launch")
        self.step_launches = seeded(initial["step2_launch_count"], "step2")
        self.retries = seeded(initial["blind_retry_count"], "blind-retry")
        self.resources = {kind: {f"{kind}:{i}" for i in range(count)}
                          for kind, count in initial["resources"].items()}
        self.process_alive = initial["observed_process_alive"]
        self.child_alive = initial["observed_child_alive"]
        self.query_facts = {}
        self.history = []

    def effect(self, operation, origin, blind=False):
        fact = {"operation": operation, "origin": origin}
        self.effects.append(fact)
        if blind:
            self.retries.append(deepcopy(fact))
        self.history.append({"event": "target_effect", **fact})

    def release(self, kinds):
        for kind in kinds:
            self.resources[kind].clear()
        self.history.append({"event": "resources_released", "kinds": list(kinds)})

    def evidence(self):
        return {"effects": deepcopy(self.effects), "model_calls": deepcopy(self.model_calls),
                "launches": deepcopy(self.launches), "step_launches": deepcopy(self.step_launches),
                "blind_retries": deepcopy(self.retries), "queries": deepcopy(self.query_facts),
                "resource_entities": {k: sorted(v) for k, v in self.resources.items()},
                "process_alive": self.process_alive, "child_alive": self.child_alive,
                "history": deepcopy(self.history)}
