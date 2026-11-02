"""Tests for the generation API service (SCRUM-8 boundary).

Exercises the HTTP boundary against scratch SQLite plus temp file
stores: asset proposals, run tracking, validation errors, and the
SCRUM-9 stage/lesson stubs. No model credentials, no live services.
"""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "database"))
sys.path.insert(0, os.path.join(ROOT, "service"))

import DataModels as db
from evolvingclass_pipeline.app import create_app  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _payload(**overrides):
    body = {
        "kind": "text",
        "title": "Gravity",
        "objectives": ["falling bodies"],
        "tags": [{"taxonomy": "subject", "value": "physics"}],
        "directives": [{
            "id": 11, "kind": "brief", "focus": "intro",
            "constraints": {}, "priority": 1,
        }],
        "parameters": {},
    }
    body.update(overrides)
    return body


class ApiGenerateTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.url = f"sqlite:///{self.db_path}"
        engine = db.get_engine(self.url)
        db.Base.metadata.create_all(engine)
        engine.dispose()
        self.content_root = tempfile.mkdtemp(prefix="ec-api-content-")
        self.preview_root = tempfile.mkdtemp(prefix="ec-api-preview-")
        sessions = db.get_session_factory(self.url)
        session = sessions()
        user = db.AppUser(role=db.UserRole.teacher, display_name="T",
                          login_ref="t@t.t")
        student = db.AppUser(role=db.UserRole.student, display_name="S",
                             login_ref="s@s.s")
        session.add_all([user, student])
        session.flush()
        school = db.School(name="Pilot School")
        session.add(school)
        session.flush()
        room = db.Classroom(school_id=school.id, name="Room 1")
        session.add(room)
        session.flush()
        session.add_all([
            db.Membership(user_id=user.id, classroom_id=room.id,
                          status=db.MembershipStatus.active),
            db.Membership(user_id=student.id, classroom_id=room.id,
                          status=db.MembershipStatus.active),
        ])
        lesson = db.Lesson(school_id=school.id, classroom_id=room.id,
                           subject="science", title="Volcanoes")
        session.add(lesson)
        session.commit()
        self.user_id = user.id
        self.student_id = student.id
        self.lesson_id = lesson.id
        session.close()
        self.app = create_app(self.url, self.content_root,
                              self.preview_root)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        os.remove(self.db_path)
        shutil.rmtree(self.content_root, ignore_errors=True)
        shutil.rmtree(self.preview_root, ignore_errors=True)

    def _propose(self, **overrides):
        body = _payload(**overrides)
        body.setdefault("created_by_id", self.user_id)
        return self.client.post("/api/generate/asset", json=body)

    def test_health_ok(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])

    def test_asset_miss_records_draft_and_completed_run(self):
        resp = self._propose()
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["message"], "Proposal recorded.")
        self.assertFalse(payload["reused"])
        for key in ("asset_id", "version_id", "version_no", "run_id",
                    "preview_ref"):
            self.assertIn(key, payload)
        self.assertEqual(payload["version_no"], 1)

        sessions = db.get_session_factory(self.url)
        session = sessions()
        try:
            version = session.get(db.AssetVersion, payload["version_id"])
            self.assertEqual(version.status, db.VersionStatus.draft)
            self.assertIn("Library miss", version.rationale)
            run = session.get(db.GenerationRun, payload["run_id"])
            self.assertEqual(run.status, db.GenerationStatus.completed)
        finally:
            session.close()

        detail = self.client.get(f"/api/runs/{payload['run_id']}")
        self.assertEqual(detail.status_code, 200)
        run = detail.get_json()["run"]
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["agent_ref"], "template-backend/v1")

    def test_second_identical_propose_misses_again(self):
        # Drafts are not published, so the library still misses; the
        # published-reuse path stays covered by the pipeline unit tests.
        first = self._propose().get_json()
        second = self._propose().get_json()
        self.assertFalse(second["reused"])
        self.assertNotEqual(second["asset_id"], first["asset_id"])

    def test_invalid_kind_title_and_shapes_rejected(self):
        for body, marker in [
            ({"kind": "nope", "title": "T", "created_by_id": 1},
             "kind"),
            ({"kind": "text", "title": "  ", "created_by_id": 1},
             "title"),
            ({"kind": "text", "created_by_id": 1}, "title"),
            ({"kind": "text", "title": "T"}, "created_by_id"),
            ({"kind": "text", "title": "T", "created_by_id": 1,
              "objectives": "nope"}, "objectives"),
            ({"kind": "text", "title": "T", "created_by_id": 1,
              "tags": [{"taxonomy": "subject"}]}, "tag"),
            ({"kind": "text", "title": "T", "created_by_id": 1,
              "directives": [{"id": 1, "kind": "brief"}]}, "directive"),
            ({"kind": "text", "title": "T", "created_by_id": 1,
              "directives": [{"id": 1, "kind": "nope", "focus": "f"}]},
             "directive"),
            ("not-an-object", "object"),
        ]:
            resp = self.client.post("/api/generate/asset", json=body)
            self.assertEqual(resp.status_code, 400, body)
            payload = resp.get_json()
            self.assertEqual(payload["code"], "invalid_request")
            self.assertIn(marker, payload["error"])

    def test_unknown_actor_is_404_without_recording_run(self):
        resp = self._propose(created_by_id=4242)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json()["code"], "unknown_actor")
        runs = self.client.get("/api/runs").get_json()["runs"]
        self.assertEqual(runs, [])

    def _asset_version_id(self, title):
        body = _payload(title=title)
        body["created_by_id"] = self.user_id
        resp = self.client.post("/api/generate/asset", json=body)
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()["version_id"]

    def _stage_body(self, **overrides):
        body = {
            "lesson_id": self.lesson_id,
            "title": "Eruption",
            "objectives": ["model the vent"],
            "asset_version_ids": [],
            "directives": [{
                "id": 11, "kind": "brief", "focus": "stage it",
                "constraints": {}, "priority": 1,
            }],
            "parameters": {},
            "created_by_id": self.user_id,
        }
        body.update(overrides)
        return body

    def _brief_body(self, **overrides):
        body = {
            "lesson_id": self.lesson_id,
            "created_by_id": self.user_id,
            "objectives": ["eruptions"],
            "mental_models": ["Magma rises."],
            "focus": "Cover the three eruption stages in order.",
            "constraints": {},
            "priority": 1,
            "student_id": None,
        }
        body.update(overrides)
        return body

    def test_stage_assembly_records_draft_uses_and_run(self):
        first = self._asset_version_id("Backdrop Rock")
        second = self._asset_version_id("Vent Diagram")
        resp = self.client.post("/api/generate/stage", json=self._stage_body(
            asset_version_ids=[first, second]))
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["message"], "Stage assembly recorded.")
        self.assertEqual(payload["version_no"], 1)

        sessions = db.get_session_factory(self.url)
        session = sessions()
        try:
            version = session.get(db.StageVersion, payload["version_id"])
            self.assertEqual(version.status, db.VersionStatus.draft)
            self.assertIn("Template assembly", version.rationale)
            self.assertEqual(version.generation_run_id, payload["run_id"])
            snapshot = version.directive_snapshot["directives"]
            self.assertEqual(snapshot[0]["focus"], "stage it")
            uses = sorted(version.asset_uses, key=lambda u: u.position)
            self.assertEqual(
                [(u.asset_version_id, u.role, u.position) for u in uses],
                [(first, "backdrop", 1), (second, "prop", 2)],
            )
            run = session.get(db.GenerationRun, payload["run_id"])
            self.assertEqual(run.status, db.GenerationStatus.completed)
            self.assertEqual(run.agent_ref, "template-stage/v1")
        finally:
            session.close()

    def test_stage_validation_errors(self):
        vid = self._asset_version_id("Solo Rock")
        cases = [
            ({"title": "  "}, 400, "invalid_request"),
            ({"title": "T", "lesson_id": "x"}, 400, "invalid_request"),
            ({"title": "T", "created_by_id": 4242}, 404, "unknown_actor"),
            ({"title": "T", "asset_version_ids": "x"}, 400,
             "invalid_request"),
            ({"title": "T", "asset_version_ids": ["x"]}, 400,
             "invalid_request"),
            ({"title": "T", "objectives": "x"}, 400, "invalid_request"),
        ]
        for overrides, status, code in cases:
            body = self._stage_body(**overrides)
            body.setdefault("asset_version_ids", [vid])
            resp = self.client.post("/api/generate/stage", json=body)
            self.assertEqual(resp.status_code, status, overrides)
            self.assertEqual(resp.get_json()["code"], code)

    def test_stage_unknown_refs_404_and_failed_run_recorded(self):
        vid = self._asset_version_id("Solo Rock")
        resp = self.client.post("/api/generate/stage", json=self._stage_body(
            lesson_id=4242, asset_version_ids=[vid]))
        self.assertEqual(resp.status_code, 404)
        resp = self.client.post("/api/generate/stage", json=self._stage_body(
            asset_version_ids=[4242]))
        self.assertEqual(resp.status_code, 404)
        failed = self.client.get("/api/runs?status=failed").get_json()
        self.assertEqual(len(failed["runs"]), 2)
        self.assertIn("LookupError", failed["runs"][0]["last_error"])

    def test_lesson_records_draft_run_and_models(self):
        resp = self.client.post("/api/generate/lesson",
                                json=self._brief_body())
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["message"], "Lesson draft recorded.")
        self.assertEqual(payload["version_no"], 1)

        sessions = db.get_session_factory(self.url)
        session = sessions()
        try:
            draft = session.get(db.LessonVersion,
                                payload["lesson_version_id"])
            self.assertEqual(draft.status, db.VersionStatus.draft)
            self.assertEqual(draft.generation_run_id, payload["run_id"])
            self.assertIsNone(draft.student_scope_id)
            models = session.scalars(
                select(db.MentalModel).where(
                    db.MentalModel.lesson_version_id == draft.id)
            ).all()
            self.assertEqual(
                [m.statement for m in models], ["Magma rises."])
            run = session.get(db.GenerationRun, payload["run_id"])
            self.assertEqual(run.status, db.GenerationStatus.completed)
            self.assertEqual(run.agent_ref, "brief-composer")
        finally:
            session.close()

    def test_lesson_student_variant_scoped(self):
        resp = self.client.post("/api/generate/lesson", json=self._brief_body(
            student_id=self.student_id))
        self.assertEqual(resp.status_code, 200)
        sessions = db.get_session_factory(self.url)
        session = sessions()
        try:
            draft = session.get(
                db.LessonVersion, resp.get_json()["lesson_version_id"])
            self.assertEqual(draft.student_scope_id, self.student_id)
        finally:
            session.close()

    def test_lesson_brief_errors(self):
        resp = self.client.post("/api/generate/lesson",
                                json=self._brief_body(focus="  "))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["code"], "invalid_brief")
        resp = self.client.post("/api/generate/lesson",
                                json=self._brief_body(lesson_id=4242))
        self.assertEqual(resp.status_code, 404)
        resp = self.client.post(
            "/api/generate/lesson",
            json=self._brief_body(created_by_id=self.student_id))
        self.assertEqual(resp.status_code, 403)
        for body, marker in [
            ({"lesson_id": "x", "created_by_id": 1, "focus": "f"},
             "lesson_id"),
            ({"lesson_id": 1, "focus": "f"}, "created_by_id"),
            ({"lesson_id": 1, "created_by_id": 1, "focus": "f",
              "objectives": "x"}, "objectives"),
            ({"lesson_id": 1, "created_by_id": 1, "focus": "f",
              "student_id": "x"}, "student_id"),
            ("not-an-object", "object"),
        ]:
            resp = self.client.post("/api/generate/lesson", json=body)
            self.assertEqual(resp.status_code, 400, body)
            self.assertIn(marker, resp.get_json()["error"])

    def test_runs_list_newest_first_with_status_filter(self):
        first = self._propose(title="One").get_json()
        second = self._propose(title="Two").get_json()
        runs = self.client.get("/api/runs").get_json()["runs"]
        self.assertEqual([r["id"] for r in runs],
                         [second["run_id"], first["run_id"]])
        for row in runs:
            for key in ("agent_ref", "model_ref", "prompt_ref", "status",
                        "attempts", "params", "policy_version"):
                self.assertIn(key, row)
        completed = self.client.get("/api/runs?status=completed")
        self.assertEqual(len(completed.get_json()["runs"]), 2)
        failed = self.client.get("/api/runs?status=failed")
        self.assertEqual(failed.get_json()["runs"], [])
        limited = self.client.get("/api/runs?limit=1")
        self.assertEqual(len(limited.get_json()["runs"]), 1)
        bad = self.client.get("/api/runs?status=nope")
        self.assertEqual(bad.status_code, 400)
        bad_limit = self.client.get("/api/runs?limit=nope")
        self.assertEqual(bad_limit.status_code, 400)

    def test_failed_run_visible_with_error(self):
        runs_store = self.app.config["runs"]
        run_id = runs_store.begin_run("probe/v1", "probe-model", "p/v1",
                                      {"q": 1}, "policy/v1")
        runs_store.mark_failed(run_id, "ValueError: probe broke")
        resp = self.client.get(f"/api/runs/{run_id}")
        self.assertEqual(resp.status_code, 200)
        run = resp.get_json()["run"]
        self.assertEqual(run["status"], "failed")
        self.assertIn("probe broke", run["last_error"])
        listed = self.client.get("/api/runs?status=failed")
        self.assertEqual(
            [r["id"] for r in listed.get_json()["runs"]], [run_id])

    def test_unknown_run_is_404(self):
        resp = self.client.get("/api/runs/4242")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
