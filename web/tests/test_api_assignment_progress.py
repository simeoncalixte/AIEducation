"""Tests for the JSON assignment-progress API (SCRUM-185).

Mirrors /assignments/<id> plus the verdict-override and
misconception-flag actions through /api: the React progress page
drives these endpoints with the same pilot semantics (staff only,
per-student attempts/verdicts/ratings/flags, unknown assignment is
404, actions return the refreshed progress in the same session).
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


class ApiAssignmentProgressTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self._tmp = tmp.name
        self.url = f"sqlite:///{tmp.name}"
        self.ids = seed(self.url)
        self.app = create_app(self.url)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        os.unlink(self._tmp)

    def login(self, login_ref):
        return self.client.post("/api/login", json={"login_ref": login_ref})

    def _assign(self):
        options = self.client.get("/api/assignments").get_json()["options"]
        resp = self.client.post("/api/assignments", json={
            "lesson_id": str(self.ids["lesson_id"]),
            "classroom_id": str(options["classrooms"][0]["id"]),
            "student_id": ""})
        return resp.get_json()["assignment_id"]

    def _add_play(self, assignment_id):
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        with factory() as session, session.begin():
            lesson_v = session.scalar(
                select(m.LessonVersion)
                .where(m.LessonVersion.status == m.VersionStatus.published)
                .order_by(m.LessonVersion.id))
            goal_id = session.scalar(select(m.Goal.id))
            attempt = m.Attempt(
                assignment_id=assignment_id,
                student_id=self.ids["student_id"],
                pinned_lesson_version_id=lesson_v.id)
            session.add(attempt)
            session.flush()
            session.add(m.ExperienceEvent(
                attempt_id=attempt.id, client_event_id="v1",
                sequence_no=1, origin=m.EventOrigin.server,
                actor_id=self.ids["teacher_id"], verb="goal-verdict",
                object_type="goal", object_ref="crater", goal_id=goal_id,
                payload={"passed": False}))
            session.add(m.Rating(
                lesson_version_id=lesson_v.id,
                author_id=self.ids["student_id"], score=4))
            attempt_id = attempt.id
            verdict_id = session.scalar(
                select(m.ExperienceEvent.id)
                .where(m.ExperienceEvent.attempt_id == attempt.id,
                       m.ExperienceEvent.verb == "goal-verdict"))
            misc_id = session.scalar(select(m.Misconception.id))
        engine.dispose()
        return attempt_id, verdict_id, misc_id

    def _progress(self, assignment_id):
        resp = self.client.get(f"/api/assignments/{assignment_id}")
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()["progress"]

    def test_progress_requires_login_as_json(self):
        resp = self.client.get("/api/assignments/1")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())
        resp = self.client.post("/api/verdicts/1/override",
                                json={"reason": "x", "corrected": "pass"})
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())
        resp = self.client.post("/api/attempts/1/flag", json={"note": "x"})
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())

    def test_progress_forbidden_for_students_as_json(self):
        self.login("sam")
        resp = self.client.get("/api/assignments/1")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("teachers and admins", resp.get_json()["error"])
        resp = self.client.post("/api/verdicts/1/override",
                                json={"reason": "x", "corrected": "pass"})
        self.assertEqual(resp.status_code, 403)
        resp = self.client.post("/api/attempts/1/flag", json={"note": "x"})
        self.assertEqual(resp.status_code, 403)

    def test_unknown_assignment_is_404_as_json(self):
        self.login("tess")
        resp = self.client.get("/api/assignments/9999")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json()["error"], "Unknown assignment")

    def test_progress_shows_verdicts_rating_and_flags(self):
        self.login("tess")
        aid = self._assign()
        attempt_id, verdict_id, _ = self._add_play(aid)
        progress = self._progress(aid)
        self.assertEqual(progress["lesson"], "Volcanoes")
        self.assertIn("Room 1", progress["target"])
        students = {row["name"]: row for row in progress["students"]}
        self.assertIn("Sam", students)
        sam = students["Sam"]
        self.assertEqual(sam["rating"], 4)
        self.assertEqual(len(sam["attempts"]), 1)
        attempt = sam["attempts"][0]
        self.assertEqual(attempt["id"], attempt_id)
        self.assertEqual(len(attempt["verdicts"]), 1)
        verdict = attempt["verdicts"][0]
        self.assertEqual(verdict["event_id"], verdict_id)
        self.assertEqual(verdict["goal"], "crater")
        self.assertFalse(verdict["passed"])
        self.assertFalse(verdict["overridden"])
        self.assertEqual(attempt["flags"], [])
        self.assertTrue(progress["misconceptions"])
        for misc in progress["misconceptions"]:
            self.assertIn("id", misc)
            self.assertIn("label", misc)

    def test_override_reflects_in_progress_same_session(self):
        self.login("tess")
        aid = self._assign()
        _, verdict_id, _ = self._add_play(aid)
        resp = self.client.post(
            f"/api/verdicts/{verdict_id}/override",
            json={"reason": "Reread.", "corrected": "pass", "score": 0.9})
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["message"], "Override recorded.")
        verdict = payload["progress"]["students"][0]["attempts"][0][
            "verdicts"][0]
        self.assertTrue(verdict["passed"])
        self.assertTrue(verdict["overridden"])
        self.assertEqual(verdict["override_reason"], "Reread.")
        # A fresh read in the same session shows the same correction.
        verdict = self._progress(aid)["students"][0]["attempts"][0][
            "verdicts"][0]
        self.assertTrue(verdict["passed"])
        self.assertIn("Reread.", verdict["override_reason"])

    def test_flag_reflects_in_progress_same_session(self):
        self.login("tess")
        aid = self._assign()
        attempt_id, _, misc_id = self._add_play(aid)
        resp = self.client.post(
            f"/api/attempts/{attempt_id}/flag", json={"note": "Said lava."})
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["message"], "Flag recorded.")
        flags = payload["progress"]["students"][0]["attempts"][0]["flags"]
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["note"], "Said lava.")
        # A misconception-typed flag records its reference too.
        resp = self.client.post(
            f"/api/attempts/{attempt_id}/flag",
            json={"misconception_id": str(misc_id), "note": "Probe missed."})
        self.assertEqual(resp.status_code, 200)
        flags = resp.get_json()["progress"]["students"][0]["attempts"][0][
            "flags"]
        self.assertEqual(len(flags), 2)
        self.assertEqual(flags[1]["ref"], str(misc_id))
        self.assertEqual(flags[1]["note"], "Probe missed.")

    def test_override_requires_reason(self):
        self.login("tess")
        aid = self._assign()
        _, verdict_id, _ = self._add_play(aid)
        resp = self.client.post(
            f"/api/verdicts/{verdict_id}/override",
            json={"reason": "  ", "corrected": "pass"})
        self.assertEqual(resp.status_code, 400)
        payload = resp.get_json()
        self.assertEqual(payload["code"], "invalid_feedback")
        self.assertIn("invalid_feedback", payload["error"])
        verdict = self._progress(aid)["students"][0]["attempts"][0][
            "verdicts"][0]
        self.assertFalse(verdict["overridden"])

    def test_flag_requires_content(self):
        self.login("tess")
        aid = self._assign()
        attempt_id, _, _ = self._add_play(aid)
        resp = self.client.post(
            f"/api/attempts/{attempt_id}/flag", json={"note": "  "})
        self.assertEqual(resp.status_code, 400)
        payload = resp.get_json()
        self.assertEqual(payload["code"], "invalid_feedback")
        self.assertIn("invalid_feedback", payload["error"])
        flags = self._progress(aid)["students"][0]["attempts"][0]["flags"]
        self.assertEqual(flags, [])

    def test_unknown_verdict_and_attempt_are_404_as_json(self):
        self.login("tess")
        resp = self.client.post(
            "/api/verdicts/9999/override",
            json={"reason": "x", "corrected": "pass"})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json()["code"], "not_found")
        resp = self.client.post("/api/attempts/9999/flag",
                                json={"note": "x"})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json()["code"], "not_found")


if __name__ == "__main__":
    unittest.main()
