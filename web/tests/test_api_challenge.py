"""Tests for the JSON challenge API (SCRUM-187).

Mirrors /play/attempt/<id>/challenge/<n> (challenge.html) through
/api/play/attempt/<id>/challenge/<n>: the React challenge page drives
these endpoints with the same pilot semantics (progress indicator
with goals; answering posts telemetry and advances; bad index is
404; owner-only with teacher read-only preview).
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


class ApiChallengeTestCase(unittest.TestCase):
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

    def test_challenge_requires_login_as_json(self):
        resp = self.client.get("/api/play/attempt/1/challenge/1")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())
        resp = self.client.post("/api/play/attempt/1/challenge/1/answer",
                                json={"goals": ["crater"]})
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())

    def test_challenge_shows_progress_and_goals(self):
        self._publish_challenge_lesson()
        aid = self._assign()
        self.login("sam")
        attempt_id = self._start(aid)
        resp = self.client.get(
            f"/api/play/attempt/{attempt_id}/challenge/1")
        self.assertEqual(resp.status_code, 200)
        challenge = resp.get_json()["challenge"]
        self.assertEqual(challenge["attempt_id"], attempt_id)
        self.assertEqual(challenge["assignment_id"], aid)
        self.assertEqual(challenge["index"], 1)
        self.assertEqual(challenge["total"], 1)
        self.assertEqual(challenge["stage"], "Eruption")
        self.assertEqual(challenge["title"], "Label the Parts")
        self.assertEqual(
            challenge["goals"],
            [{"key": "crater", "answered": False},
             {"key": "vent", "answered": False}])
        self.assertFalse(challenge["finished"])
        self.assertFalse(challenge["preview"])

    def test_answer_posts_telemetry_and_advances(self):
        self._publish_challenge_lesson()
        aid = self._assign()
        self.login("sam")
        attempt_id = self._start(aid)
        resp = self.client.post(
            f"/api/play/attempt/{attempt_id}/challenge/1/answer",
            json={"goals": ["crater"], "note": "labeled it"})
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload["next"].endswith(
            f"/play/attempt/{attempt_id}/debrief"))
        body = self.client.get(payload["next"]).get_data(as_text=True)
        for marker in ("crater", "pass", "vent", "fail"):
            self.assertIn(marker, body)
        answered = self.client.get(
            f"/api/play/attempt/{attempt_id}/challenge/1"
        ).get_json()["challenge"]["goals"]
        self.assertEqual(
            answered,
            [{"key": "crater", "answered": True},
             {"key": "vent", "answered": False}])

    def test_bad_index_is_404_as_json(self):
        self._publish_challenge_lesson()
        aid = self._assign()
        self.login("sam")
        attempt_id = self._start(aid)
        resp = self.client.get(
            f"/api/play/attempt/{attempt_id}/challenge/9")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Unknown challenge", resp.get_json()["error"])
        resp = self.client.post(
            f"/api/play/attempt/{attempt_id}/challenge/9/answer",
            json={"goals": ["crater"]})
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Unknown challenge", resp.get_json()["error"])

    def test_unknown_attempt_is_404_as_json(self):
        self.login("sam")
        resp = self.client.get("/api/play/attempt/9999/challenge/1")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Unknown attempt", resp.get_json()["error"])
        resp = self.client.post("/api/play/attempt/9999/challenge/1/answer",
                                json={"goals": ["crater"]})
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Unknown attempt", resp.get_json()["error"])

    def test_attempt_isolation_between_students(self):
        self._publish_challenge_lesson()
        aid = self._assign()
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        with factory() as session, session.begin():
            second = m.AppUser(role=m.UserRole.student,
                               display_name="Sam2", login_ref="sam2")
            session.add(second)
            session.flush()
            session.add(m.Membership(
                user_id=second.id, classroom_id=self.room_id,
                status=m.MembershipStatus.active))
        engine.dispose()
        self.login("sam2")
        other_id = self._start(aid)
        self.login("sam")
        resp = self.client.get(
            f"/api/play/attempt/{other_id}/challenge/1")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("another student", resp.get_json()["error"])
        resp = self.client.post(
            f"/api/play/attempt/{other_id}/challenge/1/answer",
            json={"goals": ["crater"]})
        self.assertEqual(resp.status_code, 403)
        self.assertIn("another student", resp.get_json()["error"])

    def test_teacher_can_preview_but_not_answer(self):
        self._publish_challenge_lesson()
        aid = self._assign()
        self.login("sam")
        attempt_id = self._start(aid)
        self.login("tess")
        resp = self.client.get(
            f"/api/play/attempt/{attempt_id}/challenge/1")
        self.assertEqual(resp.status_code, 200)
        challenge = resp.get_json()["challenge"]
        self.assertTrue(challenge["preview"])
        self.assertEqual(challenge["title"], "Label the Parts")
        resp = self.client.post(
            f"/api/play/attempt/{attempt_id}/challenge/1/answer",
            json={"goals": ["crater"]})
        self.assertEqual(resp.status_code, 403)
        self.assertIn("another student", resp.get_json()["error"])

    def test_answer_finished_attempt_is_rejected(self):
        self._publish_challenge_lesson()
        aid = self._assign()
        self.login("sam")
        attempt_id = self._start(aid)
        self.client.post(
            f"/api/play/attempt/{attempt_id}/challenge/1/answer",
            json={"goals": ["crater"]})
        self.client.post(f"/play/attempt/{attempt_id}/finish")
        resp = self.client.post(
            f"/api/play/attempt/{attempt_id}/challenge/1/answer",
            json={"goals": ["crater", "vent"]})
        self.assertEqual(resp.status_code, 400)
        payload = resp.get_json()
        self.assertEqual(payload["code"], "invalid_play")
        self.assertIn("invalid_play", payload["error"])
        challenge = self.client.get(
            f"/api/play/attempt/{attempt_id}/challenge/1"
        ).get_json()["challenge"]
        self.assertTrue(challenge["finished"])


if __name__ == "__main__":
    unittest.main()
