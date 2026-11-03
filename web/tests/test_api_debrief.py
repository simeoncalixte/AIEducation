"""Tests for the JSON debrief API (SCRUM-188).

Mirrors /play/attempt/<id>/debrief (debrief.html) plus rate/finish/retry
through /api/play/attempt/<id>/*: the React debrief page drives these
endpoints with the same pilot semantics (per-goal verdicts from recorded
events; rating 1-5 records enjoyment; finish closes the attempt; retry
opens a new attempt against the pinned version; owner-only with teacher
read-only preview).
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


class ApiDebriefTestCase(unittest.TestCase):
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

    def _answer(self, attempt_id, goals):
        resp = self.client.post(
            f"/api/play/attempt/{attempt_id}/challenge/1/answer",
            json={"goals": goals})
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()

    def _debrief(self, attempt_id):
        resp = self.client.get(f"/api/play/attempt/{attempt_id}/debrief")
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()["debrief"]

    def _setup_attempt(self):
        self._publish_challenge_lesson()
        aid = self._assign()
        self.login("sam")
        attempt_id = self._start(aid)
        self._answer(attempt_id, ["crater"])
        return aid, attempt_id

    def test_debrief_requires_login_as_json(self):
        resp = self.client.get("/api/play/attempt/1/debrief")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())
        for action, payload in (("rate", {"score": 5}),
                                ("finish", {}), ("retry", {})):
            resp = self.client.post(f"/api/play/attempt/1/{action}",
                                    json=payload)
            self.assertEqual(resp.status_code, 401)
            self.assertIn("error", resp.get_json())

    def test_debrief_shows_verdicts_from_recorded_events(self):
        aid, attempt_id = self._setup_attempt()
        debrief = self._debrief(attempt_id)
        self.assertEqual(debrief["attempt_id"], attempt_id)
        self.assertEqual(debrief["assignment_id"], aid)
        self.assertEqual(debrief["lesson"], "Volcanoes")
        self.assertFalse(debrief["finished"])
        self.assertIsNone(debrief["rating"])
        self.assertFalse(debrief["preview"])
        verdicts = {(row["goal"], row["passed"])
                    for row in debrief["verdicts"]}
        self.assertEqual(verdicts, {("crater", True), ("vent", False)})
        for row in debrief["verdicts"]:
            self.assertFalse(row["overridden"])

    def test_debrief_without_answers_has_no_verdicts(self):
        self._publish_challenge_lesson()
        aid = self._assign()
        self.login("sam")
        attempt_id = self._start(aid)
        debrief = self._debrief(attempt_id)
        self.assertEqual(debrief["verdicts"], [])

    def test_next_steps_name_failed_goals(self):
        _, attempt_id = self._setup_attempt()
        steps = self._debrief(attempt_id)["next_steps"]
        by_goal = {step["goal"]: step for step in steps
                   if step["kind"] == "retry_goal"}
        self.assertIn("vent", by_goal)
        self.assertNotIn("crater", by_goal)
        self.assertIn("vent", by_goal["vent"]["text"])

    def test_next_steps_advance_when_all_pass(self):
        self._publish_challenge_lesson()
        aid = self._assign()
        self.login("sam")
        attempt_id = self._start(aid)
        self._answer(attempt_id, ["crater", "vent"])
        steps = self._debrief(attempt_id)["next_steps"]
        kinds = {step["kind"] for step in steps}
        self.assertIn("advance", kinds)
        self.assertNotIn("retry_goal", kinds)

    def test_next_steps_continue_without_verdicts(self):
        self._publish_challenge_lesson()
        aid = self._assign()
        self.login("sam")
        attempt_id = self._start(aid)
        steps = self._debrief(attempt_id)["next_steps"]
        self.assertEqual([step["kind"] for step in steps], ["continue"])

    def test_rate_records_enjoyment(self):
        _, attempt_id = self._setup_attempt()
        resp = self.client.post(f"/api/play/attempt/{attempt_id}/rate",
                                json={"score": 5})
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["message"], "Rating recorded.")
        self.assertEqual(payload["debrief"]["rating"], 5)
        self.assertEqual(self._debrief(attempt_id)["rating"], 5)

    def test_rate_rejects_bad_scores(self):
        _, attempt_id = self._setup_attempt()
        for score in (0, 6, "loved it", None):
            resp = self.client.post(
                f"/api/play/attempt/{attempt_id}/rate",
                json={"score": score})
            self.assertEqual(resp.status_code, 400)
            payload = resp.get_json()
            self.assertEqual(payload["code"], "invalid_play")
            self.assertIn("invalid_play", payload["error"])
        self.assertIsNone(self._debrief(attempt_id)["rating"])

    def test_finish_closes_the_attempt(self):
        _, attempt_id = self._setup_attempt()
        resp = self.client.post(f"/api/play/attempt/{attempt_id}/finish")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["message"], "Attempt finished.")
        self.assertTrue(payload["debrief"]["finished"])
        self.assertTrue(self._debrief(attempt_id)["finished"])
        resp = self.client.post(f"/api/play/attempt/{attempt_id}/finish")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["code"], "invalid_play")

    def test_retry_opens_new_attempt_on_pinned_version(self):
        _, attempt_id = self._setup_attempt()
        resp = self.client.post(f"/api/play/attempt/{attempt_id}/retry")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        new_id = payload["attempt_id"]
        self.assertNotEqual(new_id, attempt_id)
        self.assertTrue(payload["next"].endswith(
            f"/play/attempt/{new_id}/challenge/1"))
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        with factory() as session:
            old = session.get(m.Attempt, attempt_id)
            new = session.get(m.Attempt, new_id)
            self.assertEqual(new.retry_of_id, attempt_id)
            self.assertEqual(new.pinned_lesson_version_id,
                             old.pinned_lesson_version_id)
            self.assertEqual(new.assignment_id, old.assignment_id)
        engine.dispose()
        self.assertEqual(self._debrief(new_id)["verdicts"], [])
        self._answer(new_id, ["crater", "vent"])
        verdicts = {(row["goal"], row["passed"])
                    for row in self._debrief(new_id)["verdicts"]}
        self.assertEqual(verdicts, {("crater", True), ("vent", True)})

    def test_unknown_attempt_is_404_as_json(self):
        self.login("sam")
        resp = self.client.get("/api/play/attempt/9999/debrief")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Unknown attempt", resp.get_json()["error"])
        for action, payload in (("rate", {"score": 5}),
                                ("finish", {}), ("retry", {})):
            resp = self.client.post(f"/api/play/attempt/9999/{action}",
                                    json=payload)
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
        resp = self.client.get(f"/api/play/attempt/{other_id}/debrief")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("another student", resp.get_json()["error"])
        for action, payload in (("rate", {"score": 5}),
                                ("finish", {}), ("retry", {})):
            resp = self.client.post(f"/api/play/attempt/{other_id}/{action}",
                                    json=payload)
            self.assertEqual(resp.status_code, 403)
            self.assertIn("another student", resp.get_json()["error"])

    def test_teacher_can_preview_but_not_mutate(self):
        _, attempt_id = self._setup_attempt()
        self.login("tess")
        resp = self.client.get(f"/api/play/attempt/{attempt_id}/debrief")
        self.assertEqual(resp.status_code, 200)
        debrief = resp.get_json()["debrief"]
        self.assertTrue(debrief["preview"])
        self.assertEqual(debrief["lesson"], "Volcanoes")
        self.assertEqual(len(debrief["verdicts"]), 2)
        for action, payload in (("rate", {"score": 5}),
                                ("finish", {}), ("retry", {})):
            resp = self.client.post(
                f"/api/play/attempt/{attempt_id}/{action}", json=payload)
            self.assertEqual(resp.status_code, 403)
            self.assertIn("another student", resp.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
