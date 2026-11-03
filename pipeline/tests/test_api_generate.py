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
from sqlalchemy import func, select  # noqa: E402


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

    def test_challenge_proposal_persists_telemetry_goals(self):
        resp = self._propose(kind="challenge", title="Label the Crater")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        sessions = db.get_session_factory(self.url)
        session = sessions()
        try:
            version = session.get(db.AssetVersion, payload["version_id"])
            self.assertEqual(version.asset.kind, db.AssetKind.challenge)
            goals = list(session.scalars(
                select(db.Goal).where(
                    db.Goal.challenge_version_id == version.id)))
            self.assertEqual(len(goals), 1)
            rule = dict(goals[0].rule)
            self.assertEqual(rule["verb"], "goal-attempted")
            self.assertEqual(goals[0].evaluation,
                             db.GoalEvaluation.deterministic)
            self.assertTrue(goals[0].template_ref)
        finally:
            session.close()

    def test_character_proposal_persists_bounded_dialogue(self):
        resp = self._propose(kind="character", title="Manager")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        sessions = db.get_session_factory(self.url)
        session = sessions()
        try:
            version = session.get(db.AssetVersion, payload["version_id"])
            self.assertEqual(version.asset.kind, db.AssetKind.character)
            self.assertEqual(version.status, db.VersionStatus.draft)
        finally:
            session.close()

    def _seed_probe_targets(self):
        sessions = db.get_session_factory(self.url)
        session = sessions()
        with session.begin():
            lesson_v = db.LessonVersion(
                lesson_id=self.lesson_id, version_no=1,
                status=db.VersionStatus.draft, rationale="r",
                objective_refs=[])
            session.add(lesson_v)
            session.flush()
            model = db.MentalModel(lesson_version_id=lesson_v.id,
                                   position=1, statement="Magma rises.")
            session.add(model)
            session.flush()
            misc = db.Misconception(
                mental_model_id=model.id, description="Lava is cold.",
                probe_notes="Ask about temperature.")
            session.add(misc)
            session.flush()
            return model.id, misc.id

    def test_challenge_probes_persist_model_links(self):
        model_id, misc_id = self._seed_probe_targets()
        resp = self._propose(
            kind="challenge", title="Label the Crater",
            parameters={"mental_model_ids": [model_id],
                        "misconception_ids": [misc_id]})
        self.assertEqual(resp.status_code, 200)
        sessions = db.get_session_factory(self.url)
        session = sessions()
        try:
            goal = session.scalar(select(db.Goal).where(
                db.Goal.challenge_version_id ==
                resp.get_json()["version_id"]))
            self.assertEqual([m.id for m in goal.mental_models],
                             [model_id])
            self.assertEqual(
                [m.id for m in goal.probed_misconceptions], [misc_id])
        finally:
            session.close()

    def test_challenge_unknown_probe_target_is_404(self):
        resp = self._propose(
            kind="challenge", title="Label the Crater",
            parameters={"mental_model_ids": [4242]})
        self.assertEqual(resp.status_code, 404)

    def test_challenge_teacher_goals_persist_with_rubric(self):
        resp = self._propose(
            kind="challenge", title="Explain Eruptions",
            parameters={"teacher_goals": [
                {"key": "explain",
                 "rubric": {"criteria": ["names magma"]}}]})
        self.assertEqual(resp.status_code, 200)
        sessions = db.get_session_factory(self.url)
        session = sessions()
        try:
            goals = list(session.scalars(
                select(db.Goal)
                .where(db.Goal.challenge_version_id ==
                       resp.get_json()["version_id"])
                .order_by(db.Goal.key)))
            teacher = [g for g in goals
                       if g.evaluation == db.GoalEvaluation.teacher]
            self.assertEqual(len(teacher), 1)
            self.assertEqual(dict(teacher[0].rubric),
                             {"criteria": ["names magma"]})
        finally:
            session.close()

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

    def _lesson_version_id(self, status=db.VersionStatus.draft):
        sessions = db.get_session_factory(self.url)
        session = sessions()
        with session.begin():
            top = session.scalar(
                select(func.max(db.LessonVersion.version_no)).where(
                    db.LessonVersion.lesson_id == self.lesson_id)
            ) or 0
            version = db.LessonVersion(
                lesson_id=self.lesson_id, version_no=top + 1,
                status=status, rationale="r", objective_refs=[])
            session.add(version)
            session.flush()
            return version.id

    def test_stage_pins_into_lesson_composition_in_order(self):
        draft_id = self._lesson_version_id()
        first = self.client.post(
            "/api/generate/stage",
            json=self._stage_body(title="Eruption",
                                  lesson_version_id=draft_id))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json()["lesson_version_id"], draft_id)
        self.assertEqual(first.get_json()["composition_position"], 1)
        second = self.client.post(
            "/api/generate/stage",
            json=self._stage_body(title="Aftermath",
                                  lesson_version_id=draft_id))
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.get_json()["composition_position"], 2)
        sessions = db.get_session_factory(self.url)
        session = sessions()
        try:
            pins = list(session.scalars(
                select(db.LessonVersionStage)
                .where(db.LessonVersionStage.lesson_version_id ==
                       draft_id)
                .order_by(db.LessonVersionStage.position)))
            self.assertEqual(
                [(p.stage_version_id, p.position) for p in pins],
                [(first.get_json()["version_id"], 1),
                 (second.get_json()["version_id"], 2)])
        finally:
            session.close()

    def test_stage_pin_rejections(self):
        resp = self.client.post(
            "/api/generate/stage",
            json=self._stage_body(title="T", lesson_version_id="x"))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["code"], "invalid_request")
        resp = self.client.post(
            "/api/generate/stage",
            json=self._stage_body(title="T", lesson_version_id=4242))
        self.assertEqual(resp.status_code, 404)
        live_id = self._lesson_version_id(
            status=db.VersionStatus.published)
        resp = self.client.post(
            "/api/generate/stage",
            json=self._stage_body(title="T",
                                  lesson_version_id=live_id))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["code"], "invalid_request")

    def test_scoped_variant_accepts_composition_pins(self):
        brief = self.client.post(
            "/api/generate/lesson",
            json=self._brief_body(student_id=self.student_id))
        self.assertEqual(brief.status_code, 200)
        variant_id = brief.get_json()["lesson_version_id"]
        stage = self.client.post(
            "/api/generate/stage",
            json=self._stage_body(title="Targeted",
                                  lesson_version_id=variant_id))
        self.assertEqual(stage.status_code, 200)
        self.assertEqual(stage.get_json()["composition_position"], 1)
        sessions = db.get_session_factory(self.url)
        session = sessions()
        try:
            variant = session.get(db.LessonVersion, variant_id)
            self.assertEqual(variant.student_scope_id, self.student_id)
            pins = list(session.scalars(
                select(db.LessonVersionStage).where(
                    db.LessonVersionStage.lesson_version_id ==
                    variant_id)))
            self.assertEqual(len(pins), 1)
            self.assertEqual(pins[0].stage_version_id,
                             stage.get_json()["version_id"])
        finally:
            session.close()

    def _seed_manager(self, status=db.VersionStatus.published):
        sessions = db.get_session_factory(self.url)
        session = sessions()
        with session.begin():
            asset = db.Asset(kind=db.AssetKind.character,
                             title="Manager",
                             created_by_id=self.user_id)
            session.add(asset)
            session.flush()
            version = db.AssetVersion(
                asset_id=asset.id, version_no=1, status=status,
                rationale="Canonical guide.", objective_refs=[],
                content_ref="content/manager-v1.json",
                param_schema={})
            session.add(version)
            session.flush()
            session.add(db.AssetTag(
                asset_version_id=version.id,
                taxonomy=db.TagTaxonomy.role, value="manager"))
            session.flush()
            return version.id

    def _stage_uses(self, version_id):
        sessions = db.get_session_factory(self.url)
        session = sessions()
        try:
            version = session.get(db.StageVersion, version_id)
            return sorted(
                ((u.asset_version_id, u.role, u.position)
                 for u in version.asset_uses),
                key=lambda row: row[2])
        finally:
            session.close()

    def test_stage_assembly_auto_pins_manager_guide_first(self):
        manager_id = self._seed_manager()
        prop = self._asset_version_id("Backdrop Rock")
        resp = self.client.post(
            "/api/generate/stage",
            json=self._stage_body(asset_version_ids=[prop]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            self._stage_uses(resp.get_json()["version_id"]),
            [(manager_id, "guide", 1), (prop, "backdrop", 2)])

    def test_stage_assembly_skips_manager_when_absent(self):
        prop = self._asset_version_id("Backdrop Rock")
        resp = self.client.post(
            "/api/generate/stage",
            json=self._stage_body(asset_version_ids=[prop]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            self._stage_uses(resp.get_json()["version_id"]),
            [(prop, "backdrop", 1)])

    def test_stage_assembly_skips_unpublished_manager(self):
        self._seed_manager(status=db.VersionStatus.draft)
        prop = self._asset_version_id("Backdrop Rock")
        resp = self.client.post(
            "/api/generate/stage",
            json=self._stage_body(asset_version_ids=[prop]))
        self.assertEqual(resp.status_code, 200)
        uses = self._stage_uses(resp.get_json()["version_id"])
        self.assertEqual(len(uses), 1)

    def test_stage_assembly_keeps_explicit_manager_use(self):
        manager_id = self._seed_manager()
        resp = self.client.post(
            "/api/generate/stage",
            json=self._stage_body(
                asset_version_ids=[manager_id],
                parameters={"roles": {str(manager_id): "host"}}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            self._stage_uses(resp.get_json()["version_id"]),
            [(manager_id, "host", 1)])

    def test_variant_inherits_manager_guide(self):
        self._seed_manager()
        brief = self.client.post(
            "/api/generate/lesson",
            json=self._brief_body(student_id=self.student_id))
        variant_id = brief.get_json()["lesson_version_id"]
        stage = self.client.post(
            "/api/generate/stage",
            json=self._stage_body(title="Targeted",
                                  lesson_version_id=variant_id))
        self.assertEqual(stage.status_code, 200)
        roles = {role for _, role, _
                 in self._stage_uses(stage.get_json()["version_id"])}
        self.assertIn("guide", roles)

    def test_stage_without_pin_leaves_composition_empty(self):
        resp = self.client.post(
            "/api/generate/stage", json=self._stage_body(title="T"))
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertIsNone(payload["lesson_version_id"])
        self.assertIsNone(payload["composition_position"])
        sessions = db.get_session_factory(self.url)
        session = sessions()
        try:
            pins = session.scalars(
                select(db.LessonVersionStage)).all()
            self.assertEqual(pins, [])
        finally:
            session.close()

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
