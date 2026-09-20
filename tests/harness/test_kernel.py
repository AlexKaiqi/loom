"""Direct contract observations for the fixed, external kernel policy."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "harnesses/kernel"))
from policy import ARCHIVE_MARKER, Kernel
from archive import encode


class KernelContract(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="loom-kernel-")
        self.work = Path(self.temporary.name) / "work"
        self.harness = self.work / "harness"
        shutil.copytree(ROOT / "harnesses/kernel", self.harness)
        shutil.copytree(self.harness / "surface", self.work / "surface")
        self.kernel = Kernel(self.harness)

    def tearDown(self):
        self.temporary.cleanup()

    def start(self, **updates):
        params = {"facts": [{"seq": 1, "kind": "work.objective.set", "payload": {"text": "Keep the original goal"}}],
                  "surface": {}, "timestamp": 123}
        params.update(updates)
        return self.kernel.start(params)

    def context(self, count=8, width=8000):
        context = self.start()["context"]
        for number in range(count):
            context["messages"].extend(self.group(number, width))
        return context

    @staticmethod
    def group(number, width):
        return [{"role": "assistant", "content": [{"type": "text", "text": str(number) + "x" * width},
                {"type": "toolCall", "id": "tool-" + str(number), "name": "shell", "arguments": {"script": "true", "target": "surface"}}],
                 "stopReason": "toolUse", "timestamp": number},
                {"role": "toolResult", "toolCallId": "tool-" + str(number), "toolName": "shell",
                 "content": [{"type": "text", "text": "verified-" + str(number)}], "isError": False, "timestamp": number}]

    def prepare(self, context):
        return self.kernel.prepare({"turn": {"context": context}})

    def reference(self, context):
        pointer = next(message for message in context["messages"] if str(message.get("content", "")).startswith(ARCHIVE_MARKER))
        return json.loads(pointer["content"][len(ARCHIVE_MARKER):])

    def original(self, reference):
        raw = (self.work / "surface" / reference["path"]).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), reference["sha256"])
        self.assertEqual(len(raw), reference["bytes"])
        return json.loads(raw)["original"]

    def test_archive_preserves_exact_original_and_recent_complete_tool_groups(self):
        context = self.context()
        original = encode(context)
        output = self.prepare(context)["context"]
        self.assertLessEqual(len(encode(output)), self.kernel.config["projection_bytes"])
        self.assertLess(len(encode(output)), len(original) // 2)
        self.assertEqual(output["messages"][0], context["messages"][0])
        self.assertEqual(output["messages"][-4:], context["messages"][-4:])
        self.assertEqual(self.original(self.reference(output)), context)
        self.assertEqual(encode(context), original)
        self.assertEqual(len((self.work / "surface/archive/index.jsonl").read_text().splitlines()), 1)

    def test_second_archive_keeps_first_archive_retrievable_without_unbounded_pointer_list(self):
        first = self.prepare(self.context())["context"]
        first_reference = self.reference(first)
        for number in range(20, 28):
            first["messages"].extend(self.group(number, 8000))
        second = self.prepare(first)["context"]
        archived = self.original(self.reference(second))
        self.assertEqual(self.reference(archived), first_reference)
        self.assertIn("Keep the original goal", json.dumps(self.original(first_reference)))
        self.assertEqual(sum(str(m.get("content", "")).startswith(ARCHIVE_MARKER) for m in second["messages"]), 1)

    def test_persistence_failure_never_returns_shrunk_context(self):
        original = self.context()
        before = encode(original)
        with patch("archive.os.fsync", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.prepare(original)
        self.assertEqual(encode(original), before)

    def test_archive_directory_cannot_redirect_to_another_location(self):
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        (self.work / "surface/archive").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.prepare(self.context())
        self.assertEqual(list(outside.iterdir()), [])

    def test_surface_boundary_cannot_be_a_symlink(self):
        outside = Path(self.temporary.name) / "outside"
        (self.work / "surface").rename(outside)
        (self.work / "surface").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.prepare(self.context())
        self.assertFalse((outside / "archive").exists())

    def test_archive_index_cannot_redirect_to_another_file(self):
        outside = Path(self.temporary.name) / "keep.txt"
        outside.write_text("must stay unchanged")
        (self.work / "surface/archive").mkdir()
        (self.work / "surface/archive/index.jsonl").symlink_to(outside)
        with self.assertRaises((OSError, ValueError)):
            self.prepare(self.context())
        self.assertEqual(outside.read_text(), "must stay unchanged")

    def test_oversized_latest_group_rejects_without_clipping_tool_results(self):
        context = self.context(count=2, width=60000)
        before = encode(context)
        with self.assertRaisesRegex(ValueError, "latest complete tool turn"):
            self.prepare(context)
        self.assertEqual(encode(context), before)

    def test_incomplete_tool_group_rejects_instead_of_returning_invalid_context(self):
        context = self.context()
        del context["messages"][2]
        with self.assertRaisesRegex(ValueError, "incomplete tool group"):
            self.prepare(context)

    def test_initial_projection_bounds_facts_and_surface_and_archives_original_facts(self):
        facts = [{"seq": i, "kind": "work.message", "payload": {"text": str(i) + "m" * 4000}} for i in range(20)]
        facts.insert(0, {"seq": 0, "kind": "work.objective.set", "payload": {"text": "Mandatory current objective"}})
        surface = {"archive/old.json": "FORBIDDEN_RECURSIVE_ARCHIVE_BODY" * 1000,
                   "plan.md": "# Plan\n- [x] Previous step; evidence report.md\n- [ ] Current step marker\n- [ ] Next step marker\n",
                   "report.md": "Existing evidence", "notes.md": "Working observations"}
        surface.update({"extra-" + str(i) + ".md": "z" * 10000 for i in range(30)})
        context = self.start(facts=facts, surface=surface)["context"]
        self.assertLessEqual(len(encode(context)), self.kernel.config["projection_bytes"] // 2)
        self.assertNotIn("FORBIDDEN_RECURSIVE_ARCHIVE_BODY", encode(context).decode())
        projected = json.loads(context["messages"][0]["content"])
        self.assertEqual(projected["surface"]["plan.md"]["current_step"], "Current step marker")
        self.assertEqual(projected["surface"]["plan.md"]["next_step"], "Next step marker")
        self.assertEqual(self.original(projected["fact_archive"]), facts)
        self.assertEqual(projected["archive_index"]["path"], "archive/index.jsonl")
        self.assertIn("Mandatory current objective", encode(context).decode())

    def test_model_window_reduces_working_set_without_changing_model(self):
        context = self.start(model_semantics={"contextWindow": 20000, "maxTokens": 2000})["context"]
        projection = json.loads(context["messages"][0]["content"])["projection"]
        self.assertLess(projection["archive_trigger_bytes"], self.kernel.config["archive_trigger_bytes"])
        self.assertLessEqual(len(encode(context)), projection["projection_bytes"] // 2)
        self.assertNotIn("model", context)

    def test_existing_4096_token_model_supports_simple_goal_and_file_pointers(self):
        surface = {path.name: path.read_text() for path in (self.work / "surface").iterdir()}
        context = self.start(model_semantics={"contextWindow": 4096, "maxTokens": 512}, surface=surface)["context"]
        projection = json.loads(context["messages"][0]["content"])["projection"]
        self.assertIn("Keep the original goal", context["messages"][0]["content"])
        self.assertLessEqual(len(encode(context)), projection["projection_bytes"] // 2)
        self.assertIn("report.md", encode(context).decode())
        self.assertGreater(projection["archive_trigger_bytes"], projection["projection_bytes"])

    def test_catalog_output_capacity_is_not_mistaken_for_this_requests_budget(self):
        plan = self.start(model_semantics={"contextWindow": 131072, "maxTokens": 131072})
        self.assertEqual(plan["options"]["maxTokens"], self.kernel.config["max_output_tokens"])
        self.assertIn("Keep the original goal", plan["context"]["messages"][0]["content"])
        small = self.start(model_semantics={"contextWindow": 4096, "maxTokens": 4096})
        self.assertEqual(small["options"]["maxTokens"], 1024)
        capped = self.start(model_semantics={"contextWindow": 4096, "maxTokens": 512})
        self.assertEqual(capped["options"]["maxTokens"], 512)

    def test_window_too_small_for_actual_mandatory_input_rejects(self):
        with self.assertRaisesRegex(ValueError, "current objective exceeds"):
            self.start(model_semantics={"contextWindow": 1024, "maxTokens": 512})
        with self.assertRaisesRegex(ValueError, "leaves no kernel input space"):
            self.start(model_semantics={"contextWindow": 1, "maxTokens": 1})

    def test_oversized_current_objective_rejects_instead_of_dropping_requirement(self):
        with self.assertRaisesRegex(ValueError, "current objective exceeds"):
            self.start(facts=[{"kind": "work.objective.set", "payload": {"text": "x" * 50000}}])

    def test_plan_checkbox_and_comment_do_not_become_verified_completion(self):
        view = self.kernel.plan_view("<!-- - [ ] Old example -->\n- [x] Claimed done\n- [ ] Real next step; evidence notes.md\n")
        self.assertEqual(view["current_step"], "Real next step; evidence notes.md")
        self.assertIn("not independently verified", view["meaning"])
        self.assertFalse(self.kernel.continuation({"turn": {"message": {"stopReason": "stop"}, "context": {"plan": view}}}))

    def test_latest_user_correction_is_mandatory_in_initial_projection(self):
        facts = [{"kind": "work.objective.set", "payload": {"text": "Original goal"}},
                 {"kind": "work.message", "payload": {"text": "Corrected requirement " + "c" * 7000}}]
        context = self.start(facts=facts)["context"]
        self.assertIn("Corrected requirement", context["messages"][0]["content"])
        facts[-1]["payload"]["text"] += "c" * 10000
        with self.assertRaisesRegex(ValueError, "current objective exceeds"):
            self.start(facts=facts)

    def test_index_hardlink_cannot_append_to_another_surface_file(self):
        outside = self.work / "surface/report.md"
        original = outside.read_bytes()
        (self.work / "surface/archive").mkdir()
        (self.work / "surface/archive/index.jsonl").hardlink_to(outside)
        with self.assertRaisesRegex(ValueError, "ordinary file with one link"):
            self.prepare(self.context())
        self.assertEqual(outside.read_bytes(), original)

    def test_below_threshold_does_not_create_archive(self):
        self.assertIsNone(self.prepare(self.context(count=1, width=10)))
        self.assertFalse((self.work / "surface/archive").exists())


if __name__ == "__main__":
    unittest.main()
