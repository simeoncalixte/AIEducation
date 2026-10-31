"""Tests for the JSON lesson-briefing API (SCRUM-186).

Mirrors /play/<id> (briefing.html) through /api/play/<id>: the React
briefing page drives these endpoints with the same pilot semantics
(lesson shape with objectives, mental models, stages, and a start
action; unpublished lessons report the not-published state; start
opens or resumes the student's attempt).
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


class ApiPlayTestCase(unittest.TestCase):
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
        engine.dispose()

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
            self.client.post(f"/review/{kind}/{vid}/approve",
                             data={"rationale": "ok"})
            resp = self.client.post(f"/review/{kind}/{vid}/publish",
                                    data={"rationale": "ship"})
            self.assertEqual(resp.status_code, 302)

    def _assign(self, lesson_id=None):
        self.login("tess")
        resp = self.client.post("/api/assignments", json={
            "lesson_id": str(lesson_id or self.ids["lesson_id"]),
            "classroom_id": str(self.room_id), "student_id": ""})
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()["assignment_id"]

    def test_play_requires_login_as_json(self):
        resp = self.client.get("/api/play/1")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())
        resp = self.client.post("/api/play/1/start")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())

    def test_briefing_shows_lesson_shape(self):
        self._publish_challenge_lesson()
        aid = self._assign()
        self.login("sam")
        resp = self.client.get(f"/api/play/{aid}")
        self.assertEqual(resp.status_code, 200)
        briefing = resp.get_json()["briefing"]
        self.assertEqual(briefing["assignment_id"], aid)
        self.assertEqual(briefing["lesson"], "Volcanoes")
        self.assertTrue(briefing["published"])
        self.assertIn("sci.eruptions", briefing["objectives"])
        self.assertTrue(any("Eruptions move magma" in model
                            for model in briefing["models"]))
        self.assertIn("Eruption", briefing["stages"])
        self.assertIsNone(briefing["open_attempt_id"])

    def test_start_opens_and_resumes_attempt(self):
        self._publish_challenge_lesson()
        aid = self._assign()
        self.login("sam")
        resp = self.client.post(f"/api/play/{aid}/start")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        attempt_id = payload["attempt_id"]
        self.assertTrue(payload["next"].endswith(
            f"/play/attempt/{attempt_id}/challenge/1"))
        briefing = self.client.get(f"/api/play/{aid}").get_json()["briefing"]
        self.assertEqual(briefing["open_attempt_id"], attempt_id)
        again = self.client.post(f"/api/play/{aid}/start").get_json()
        self.assertEqual(again["attempt_id"], attempt_id)
        self.assertEqual(again["next"], payload["next"])

    def test_start_without_challenges_goes_to_debrief(self):
        aid = self._assign()
        self.login("sam")
        payload = self.client.post(f"/api/play/{aid}/start").get_json()
        self.assertTrue(payload["next"].endswith(
            f"/play/attempt/{payload['attempt_id']}/debrief"))

    def test_unpublished_lesson_has_no_play(self):
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        with factory() as session, session.begin():
            school_id = session.scalar(select(m.School.id))
            lesson = m.Lesson(school_id=school_id,
                              classroom_id=self.room_id,
                              subject="math", title="Fractions")
            session.add(lesson)
            session.flush()
            lesson_id = lesson.id
        engine.dispose()
        aid = self._assign(lesson_id=lesson_id)
        self.login("sam")
        briefing = self.client.get(f"/api/play/{aid}").get_json()["briefing"]
        self.assertEqual(briefing["lesson"], "Fractions")
        self.assertFalse(briefing["published"])
        resp = self.client.post(f"/api/play/{aid}/start")
        self.assertEqual(resp.status_code, 400)
        payload = resp.get_json()
        self.assertEqual(payload["code"], "invalid_play")
        self.assertIn("invalid_play", payload["error"])

    def test_teacher_cannot_start_attempt(self):
        self._publish_challenge_lesson()
        aid = self._assign()
        self.login("tess")
        resp = self.client.get(f"/api/play/{aid}")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["briefing"]["published"])
        resp = self.client.post(f"/api/play/{aid}/start")
        self.assertEqual(resp.status_code, 403)
        payload = resp.get_json()
        self.assertEqual(payload["code"], "forbidden")
        self.assertIn("forbidden", payload["error"])

    def test_unknown_assignment_is_404_as_json(self):
        self.login("sam")
        resp = self.client.get("/api/play/9999")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Unknown assignment", resp.get_json()["error"])
        resp = self.client.post("/api/play/9999/start")
        self.assertEqual(resp.status_code, 404)
        payload = resp.get_json()
        self.assertEqual(payload["code"], "not_found")
        self.assertIn("not_found", payload["error"])


if __name__ == "__main__":
    unittest.main()
