"""Tests for the rubric grading view API (SCRUM-38, SCRUM-129).

Staff-only read pairing recorded evidence with rubric criteria, plus
verdict entry through the teacher-evaluation endpoint: grades surface
in the debrief and feed mastery and impact.
"""

import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "database"))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "service"))
sys.path.insert(0, os.path.join(ROOT, "web"))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import DataModels as m  # noqa: E402
from evolvingclass_web.app import create_app  # noqa: E402
from evolvingclass_web.seed import seed  # noqa: E402


class ApiGradingTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self._tmp = tmp.name
        self.url = f"sqlite:///{tmp.name}"
        self.ids = seed(self.url)
        self.app = create_app(self.url)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        with factory() as session:
            self.room_id = session.scalar(select(m.Classroom.id))
            self.explain_id = session.scalar(
                select(m.Goal.id).where(
                    m.Goal.challenge_version_id ==
                    self.ids["challenge_draft_id"],
                    m.Goal.key == "explain"))
        engine.dispose()
        self.assertIsNotNone(self.explain_id)
        self._publish_challenge_lesson()
        aid = self._assign()
        self.login("sam")
        self.attempt_id = self._start(aid)
        self._answer(self.attempt_id, ["explain"],
                     note="Magma rises through the vent.")

    def tearDown(self):
        os.unlink(self._tmp)

    def login(self, login_ref):
        return self.client.post("/api/login", json={"login_ref": login_ref})

    def _publish_challenge_lesson(self):
        with self.client.session_transaction() as sess:
            sess["actor_id"] = self.ids["teacher_id"]
        for kind, vid in (
                ("asset", self.ids["asset_draft_id"]),
                ("asset", self.ids["challenge_draft_id"]),
                ("stage", self.ids["stage_draft_id"]),
                ("lesson", self.ids["lesson_draft_id"])):
            resp = self.client.post(
                f"/api/review/{kind}/{vid}/approve",
                json={"rationale": "ok"})
            self.assertEqual(resp.status_code, 200)
            resp = self.client.post(f"/api/review/{kind}/{vid}/publish",
                                    json={"rationale": "ship"})
            self.assertEqual(resp.status_code, 200)

    def _assign(self):
        self.login("tess")
        resp = self.client.post("/api/assignments", json={
            "lesson_id": str(self.ids["lesson_id"]),
            "classroom_id": str(self.room_id), "student_id": ""})
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()["assignment_id"]

    def _start(self, aid):
        resp = self.client.post(f"/api/play/{aid}/start")
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()["attempt_id"]

    def _answer(self, attempt_id, goals, note=""):
        resp = self.client.post(
            f"/api/play/attempt/{attempt_id}/challenge/1/answer",
            json={"goals": goals, "note": note})
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()

    def _grading(self, attempt_id):
        return self.client.get(f"/api/attempts/{attempt_id}/grading")

    def _grade(self, attempt_id, goal_id, passed, rationale=""):
        return self.client.post(
            f"/api/attempts/{attempt_id}/teacher-evaluations",
            json={"goal_id": goal_id, "passed": passed,
                  "rationale": rationale})

    def test_grading_view_pairs_evidence_with_rubric(self):
        self.login("tess")
        resp = self._grading(self.attempt_id)
        self.assertEqual(resp.status_code, 200)
        grading = resp.get_json()["grading"]
        self.assertEqual(grading["attempt_id"], self.attempt_id)
        self.assertEqual(grading["student"], "Sam")
        goals = {g["key"]: g for g in grading["goals"]}
        self.assertIn("explain", goals)
        rubric = goals["explain"]["rubric"]
        self.assertTrue(rubric["criteria"])
        self.assertIsNone(goals["explain"]["evaluation"])
        notes = [e["note"] for e in grading["evidence"]]
        self.assertIn("Magma rises through the vent.", notes)

    def test_grade_records_evaluation_visible_in_debrief(self):
        self.login("tess")
        resp = self._grade(self.attempt_id, self.explain_id, True,
                           rationale="Names magma.")
        self.assertEqual(resp.status_code, 200)
        grading = self._grading(self.attempt_id).get_json()["grading"]
        goals = {g["key"]: g for g in grading["goals"]}
        evaluation = goals["explain"]["evaluation"]
        self.assertTrue(evaluation["passed"])
        self.assertEqual(evaluation["rationale"], "Names magma.")
        self.login("sam")
        resp = self.client.get(
            f"/api/play/attempt/{self.attempt_id}/debrief")
        self.assertEqual(resp.status_code, 200)
        verdicts = {row["goal"]: row
                    for row in resp.get_json()["debrief"]["verdicts"]}
        self.assertIn("explain", verdicts)
        self.assertTrue(verdicts["explain"]["passed"])
        self.assertEqual(verdicts["explain"]["source"], "teacher")

    def test_regrade_updates_debrief_latest_wins(self):
        self.login("tess")
        self.assertEqual(
            self._grade(self.attempt_id, self.explain_id, True).status_code,
            200)
        self.assertEqual(
            self._grade(self.attempt_id, self.explain_id, False,
                        rationale="Reread it.").status_code, 200)
        self.login("sam")
        resp = self.client.get(
            f"/api/play/attempt/{self.attempt_id}/debrief")
        verdicts = {row["goal"]: row
                    for row in resp.get_json()["debrief"]["verdicts"]}
        self.assertFalse(verdicts["explain"]["passed"])
        self.assertEqual(verdicts["explain"]["rationale"], "Reread it.")

    def test_grading_guards(self):
        self.login("tess")
        self.assertEqual(self._grading(9999).status_code, 404)
        self.login("sam")
        self.assertEqual(self._grading(self.attempt_id).status_code, 403)
        fresh = self.app.test_client()
        self.assertEqual(
            fresh.get(f"/api/attempts/{self.attempt_id}/grading").status_code,
            401)

    def test_teacher_evaluation_feeds_mastery_and_impact(self):
        self.login("tess")
        self.assertEqual(
            self._grade(self.attempt_id, self.explain_id, True).status_code,
            200)
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        try:
            with factory() as session:
                records = list(session.scalars(
                    select(m.MasteryRecord).where(
                        m.MasteryRecord.student_id ==
                        self.ids["student_id"])))
                self.assertTrue(records)
                self.assertTrue(all(r.score == 1.0 for r in records))
                links = list(session.scalars(
                    select(m.MasteryEvidence).where(
                        m.MasteryEvidence.source ==
                        "teacher-evaluation")))
                self.assertTrue(links)
                rollup = session.scalar(
                    select(m.ImpactRollup)
                    .where(
                        m.ImpactRollup.asset_version_id ==
                        self.ids["challenge_draft_id"],
                        m.ImpactRollup.window == "all")
                    .order_by(m.ImpactRollup.id.desc())
                    .limit(1))
                self.assertIsNotNone(rollup)
                self.assertEqual(rollup.mastery, 1.0)
                self.assertEqual(rollup.sample_size, 1)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
