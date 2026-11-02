"""Tests for the JSON telemetry intake API (SCRUM-23).

POST /api/play/attempt/<id>/events records one client telemetry event
idempotently: replays of the same client_event_id report the existing
row instead of duplicating it. Owner-only with teacher read-only
preview, mirroring the challenge answer endpoint.
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


class ApiEventsTestCase(unittest.TestCase):
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

    def _attempt(self):
        aid = self._assign()
        self.login("sam")
        return self._start(aid)

    def _post(self, attempt_id, **overrides):
        body = {"client_event_id": "evt-1", "verb": "viewed",
                "object_type": "stage", "object_ref": "eruption",
                "payload": {"t": 12}}
        body.update(overrides)
        return self.client.post(f"/api/play/attempt/{attempt_id}/events",
                                json=body)

    def _event_count(self, attempt_id):
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        with factory() as session:
            count = session.scalar(
                select(m.func.count()).select_from(m.ExperienceEvent)
                .where(m.ExperienceEvent.attempt_id == attempt_id))
        engine.dispose()
        return count

    def test_events_require_login_as_json(self):
        resp = self.client.post("/api/play/attempt/1/events",
                                json={"client_event_id": "e", "verb": "v"})
        self.assertEqual(resp.status_code, 401)

    def test_intake_records_event(self):
        attempt_id = self._attempt()
        resp = self._post(attempt_id)
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["message"], "Event recorded.")
        self.assertFalse(payload["duplicate"])
        self.assertEqual(self._event_count(attempt_id), 1)

    def test_replay_returns_existing_row(self):
        attempt_id = self._attempt()
        first = self._post(attempt_id).get_json()
        second = self._post(attempt_id,
                            payload={"t": 999}).get_json()
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["event_id"], first["event_id"])
        self.assertEqual(second["message"], "Event already recorded.")
        self.assertEqual(self._event_count(attempt_id), 1)

    def test_same_id_on_another_attempt_is_distinct(self):
        aid = self._assign()
        self.login("sam")
        first_id = self._start(aid)
        self.client.post(f"/api/play/attempt/{first_id}/finish")
        second_id = self._start(aid)
        self.assertNotEqual(second_id, first_id)
        one = self._post(first_id).get_json()
        two = self._post(second_id).get_json()
        self.assertFalse(two["duplicate"])
        self.assertNotEqual(two["event_id"], one["event_id"])

    def test_late_event_on_finished_attempt_kept(self):
        attempt_id = self._attempt()
        self.client.post(f"/api/play/attempt/{attempt_id}/finish")
        resp = self._post(attempt_id)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.get_json()["duplicate"])

    def test_unknown_attempt_is_404_as_json(self):
        self._attempt()
        resp = self._post(4242)
        self.assertEqual(resp.status_code, 404)

    def test_attempt_isolation_between_students(self):
        attempt_id = self._attempt()
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
        resp = self._post(attempt_id)
        self.assertEqual(resp.status_code, 403)
        self.assertIn("another student", resp.get_json()["error"])

    def test_teacher_cannot_post_events(self):
        attempt_id = self._attempt()
        self.login("tess")
        resp = self._post(attempt_id)
        self.assertEqual(resp.status_code, 403)

    def test_invalid_shapes_rejected_as_json(self):
        attempt_id = self._attempt()
        for overrides, marker in [
            ({"client_event_id": "  "}, "client_event_id"),
            ({"client_event_id": "x" * 101}, "client_event_id"),
            ({"verb": "  "}, "verb"),
            ({"payload": "nope"}, "payload"),
            ({"object_type": 7}, "object_type"),
        ]:
            resp = self._post(attempt_id, **overrides)
            self.assertEqual(resp.status_code, 400, overrides)
            self.assertIn(marker, resp.get_json()["error"])
        self.assertEqual(self._event_count(attempt_id), 0)


if __name__ == "__main__":
    unittest.main()
