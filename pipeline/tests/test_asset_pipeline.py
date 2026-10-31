"""Orchestrator behavior against fake ports (LSP in action)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evolvingclass_pipeline.asset_pipeline import AssetPipeline
from evolvingclass_pipeline.domain import (
    AssetKind,
    DirectiveInput,
    DirectiveKind,
    DraftRef,
    GeneratedContent,
    GenerationFailed,
    GenerationRequest,
    LibraryMatch,
    PolicyViolation,
    PreviewResult,
    Tag,
)
from evolvingclass_pipeline.policy import ContentPolicy
from evolvingclass_pipeline.ports import (
    AssetLibraryPort,
    ContentStore,
    GenerationBackend,
    PreviewPort,
    RunStore,
)


class FakeLibrary(AssetLibraryPort):
    def __init__(self, matches=()):
        self.matches = list(matches)
        self.saved = []
        self.previews = []

    def find_candidates(self, kind, tags, objectives, limit=5):
        return list(self.matches)

    def save_draft(self, content, content_ref, snapshot, run_id,
                   created_by_id, asset_id=None):
        self.saved.append(
            {"content": content, "snapshot": snapshot, "run_id": run_id})
        return DraftRef(asset_id=7, version_id=9, version_no=1)

    def record_preview(self, version_id, kind, storage_ref):
        self.previews.append(
            {"version_id": version_id, "kind": kind,
             "storage_ref": storage_ref})


class FakeBackend(GenerationBackend):
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.calls = 0

    @property
    def agent_ref(self):
        return "fake-agent/v1"

    @property
    def model_ref(self):
        return "fake-model/v1"

    def generate(self, request):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.content


class FakePreviews(PreviewPort):
    def __init__(self):
        self.requests = []

    def render(self, request):
        self.requests.append(request)
        return PreviewResult(storage_ref="p/1.svg")


class FakeRuns(RunStore):
    def __init__(self):
        self.events = []

    def begin_run(self, agent_ref, model_ref, prompt_ref, params,
                  policy_version):
        self.events.append(("begin", agent_ref, model_ref))
        return 42

    def mark_running(self, run_id):
        self.events.append(("running", run_id))

    def mark_completed(self, run_id):
        self.events.append(("completed", run_id))

    def mark_failed(self, run_id, error):
        self.events.append(("failed", run_id, error))


class FakeStore(ContentStore):
    def __init__(self):
        self.bodies = []

    def put(self, body):
        self.bodies.append(body)
        return "sha256:abc.json"

    def get(self, storage_ref):
        return self.bodies[0]


def make_request(**overrides):
    args = {
        "kind": AssetKind.text,
        "title": "Gravity",
        "objectives": ("falling bodies",),
        "tags": (Tag("subject", "physics"),),
        "directives": (DirectiveInput(
            id=3, kind=DirectiveKind.brief, focus="intro",
            constraints={}, priority=1),),
        "parameters": {},
    }
    args.update(overrides)
    return GenerationRequest(**args)


def make_content(**overrides):
    args = {
        "kind": AssetKind.text,
        "title": "Gravity",
        "body": {"text": "short"},
        "tags": (Tag("subject", "physics"),),
        "objective_refs": ("falling bodies",),
        "rationale": "r",
    }
    args.update(overrides)
    return GeneratedContent(**args)


class PipelineCase(unittest.TestCase):
    def make(self, matches=(), content=None, error=None, policy=None):
        lib, back = FakeLibrary(matches), FakeBackend(content, error)
        prev, runs, store = FakePreviews(), FakeRuns(), FakeStore()
        pipe = AssetPipeline(lib, back, prev, runs, store,
                             policy=policy or ContentPolicy())
        return pipe, lib, back, prev, runs, store

    def test_reuse_hit_skips_backend(self):
        match = LibraryMatch(7, 9, 2, 0.95, "matched")
        pipe, lib, back, prev, runs, _ = self.make(matches=[match])
        result = pipe.propose(make_request(), created_by_id=1)
        self.assertTrue(result.reused)
        self.assertEqual(back.calls, 0)
        self.assertEqual(lib.saved, [])
        self.assertEqual(result.version_no, 2)
        self.assertEqual(len(prev.requests), 1)
        self.assertEqual(lib.previews, [])
        self.assertIn(("completed", 42), runs.events)

    def test_low_score_generates(self):
        match = LibraryMatch(7, 9, 2, 0.1, "weak")
        pipe, _, back, _, runs, _ = self.make(
            matches=[match], content=make_content())
        result = pipe.propose(make_request(), created_by_id=1)
        self.assertFalse(result.reused)
        self.assertEqual(back.calls, 1)
        self.assertIn(("completed", 42), runs.events)

    def test_miss_saves_snapshot_and_preview(self):
        pipe, lib, _, prev, runs, store = self.make(
            content=make_content())
        result = pipe.propose(make_request(), created_by_id=5)
        self.assertFalse(result.reused)
        self.assertEqual(result.preview_ref, "p/1.svg")
        saved = lib.saved[0]
        self.assertEqual(saved["run_id"], 42)
        self.assertIn("Library miss", saved["content"].rationale)
        self.assertEqual(
            saved["snapshot"]["directives"],
            [{"id": 3, "kind": "brief", "focus": "intro",
              "constraints": {}, "priority": 1}],
        )
        self.assertEqual(len(store.bodies), 1)
        kinds = [e[0] for e in runs.events]
        self.assertEqual(kinds, ["begin", "running", "completed"])

    def test_miss_records_preview_for_new_draft(self):
        pipe, lib, _, _, _, _ = self.make(content=make_content())
        result = pipe.propose(make_request(), created_by_id=5)
        self.assertEqual(
            lib.previews,
            [{"version_id": result.version_id, "kind": "poster",
              "storage_ref": "p/1.svg"}])

    def test_policy_violation_blocks_draft(self):
        policy = ContentPolicy(allowed_script_hooks=frozenset())
        content = make_content(
            kind=AssetKind.script,
            body={"source": "x", "hooks": ["on_start"]},
        )
        pipe, lib, _, _, runs, _ = self.make(content=content, policy=policy)
        with self.assertRaises(PolicyViolation):
            pipe.propose(make_request(kind=AssetKind.script), created_by_id=1)
        self.assertEqual(lib.saved, [])
        self.assertTrue(
            any(e[0] == "failed" and "PolicyViolation" in e[2]
                for e in runs.events))

    def test_backend_failure_marks_run_failed(self):
        pipe, lib, _, _, runs, _ = self.make(
            error=GenerationFailed("boom"))
        with self.assertRaises(GenerationFailed):
            pipe.propose(make_request(), created_by_id=1)
        self.assertEqual(lib.saved, [])
        self.assertTrue(
            any(e[0] == "failed" and "boom" in e[2] for e in runs.events))


if __name__ == "__main__":
    unittest.main()
