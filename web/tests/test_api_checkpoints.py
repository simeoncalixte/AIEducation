"""Tests for the JSON checkpoint API (SCRUM-24).

POST /api/play/attempt/<id>/checkpoints snapshots scene/progress
state with a monotonic per-attempt sequence; GET .../latest restores
it after the client closes or the connection drops. Owner-only writes
with teacher read-only preview, mirroring the other attempt routes.
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


class ApiCheckpointsTestCase(unittest.TestCase):
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

    def _pinned_stage_version(self, attempt_id):
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        with factory() as session:
            vid = session.scalar(
                select(m.AttemptPin.stage_version_id).where(
                    m.AttemptPin.attempt_id == attempt_id))
        engine.dispose()
        self.assertIsNotNone(vid)
        return vid

    def _save(self, attempt_id, vid, state=None):
        return self.client.post(
            f"/api/play/attempt/{attempt_id}/checkpoints",
            json={"stage_version_id": vid,
                  "state": {"renderer": "web", "schema_version": 1}
                  if state is None else state})

    def test_checkpoints_require_login_as_json(self):
        resp = self.client.post("/api/play/attempt/1/checkpoints", json={})
        self.assertEqual(resp.status_code, 401)
        resp = self.client.get("/api/play/attempt/1/checkpoints/latest")
        self.assertEqual(resp.status_code, 401)

    def test_save_assigns_monotonic_sequences(self):
        attempt_id = self._attempt()
        vid = self._pinned_stage_version(attempt_id)
        first = self._save(attempt_id, vid).get_json()
        self.assertEqual(first["checkpoint_sequence"], 1)
        second = self._save(attempt_id, vid).get_json()
        self.assertEqual(second["checkpoint_sequence"], 2)
        self.assertNotEqual(second["checkpoint_id"], first["checkpoint_id"])

    def test_latest_returns_newest_snapshot(self):
        attempt_id = self._attempt()
        vid = self._pinned_stage_version(attempt_id)
        self._save(attempt_id, vid, {"renderer": "web", "at": 1})
        self._save(attempt_id, vid, {"renderer": "web", "at": 2})
        resp = self.client.get(
            f"/api/play/attempt/{attempt_id}/checkpoints/latest")
        self.assertEqual(resp.status_code, 200)
        found = resp.get_json()["checkpoint"]
        self.assertEqual(found["checkpoint_sequence"], 2)
        self.assertEqual(found["stage_version_id"], vid)
        self.assertEqual(found["state"], {"renderer": "web", "at": 2})
        self.assertFalse(found["preview"])

    def test_latest_empty_is_404(self):
        attempt_id = self._attempt()
        resp = self.client.get(
            f"/api/play/attempt/{attempt_id}/checkpoints/latest")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("No checkpoints", resp.get_json()["error"])

    def test_unknown_attempt_is_404_as_json(self):
        self._attempt()
        resp = self.client.post("/api/play/attempt/4242/checkpoints",
                                json={"stage_version_id": 1, "state": {}})
        self.assertEqual(resp.status_code, 404)
        resp = self.client.get("/api/play/attempt/4242/checkpoints/latest")
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
        resp = self.client.post(
            f"/api/play/attempt/{attempt_id}/checkpoints",
            json={"stage_version_id": 1, "state": {}})
        self.assertEqual(resp.status_code, 403)
        resp = self.client.get(
            f"/api/play/attempt/{attempt_id}/checkpoints/latest")
        self.assertEqual(resp.status_code, 403)

    def test_teacher_preview_read_only(self):
        attempt_id = self._attempt()
        vid = self._pinned_stage_version(attempt_id)
        self._save(attempt_id, vid)
        self.login("tess")
        resp = self.client.get(
            f"/api/play/attempt/{attempt_id}/checkpoints/latest")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["checkpoint"]["preview"])
        resp = self.client.post(
            f"/api/play/attempt/{attempt_id}/checkpoints",
            json={"stage_version_id": vid, "state": {}})
        self.assertEqual(resp.status_code, 403)

    def test_invalid_shapes_rejected_as_json(self):
        attempt_id = self._attempt()
        vid = self._pinned_stage_version(attempt_id)
        for body, marker in [
            ({"state": {}}, "stage_version_id"),
            ({"stage_version_id": "x", "state": {}}, "stage_version_id"),
            ({"stage_version_id": vid, "state": "x"}, "state"),
        ]:
            resp = self.client.post(
                f"/api/play/attempt/{attempt_id}/checkpoints", json=body)
            self.assertEqual(resp.status_code, 400, body)
            self.assertIn(marker, resp.get_json()["error"])

    def test_unpinned_and_unknown_stage_versions_rejected(self):
        attempt_id = self._attempt()
        vid = self._pinned_stage_version(attempt_id)
        resp = self.client.post(
            f"/api/play/attempt/{attempt_id}/checkpoints",
            json={"stage_version_id": 4242, "state": {}})
        self.assertEqual(resp.status_code, 404)
        draft_vid = self.ids["stage_draft_id"]
        self.assertNotEqual(draft_vid, vid)
        resp = self.client.post(
            f"/api/play/attempt/{attempt_id}/checkpoints",
            json={"stage_version_id": draft_vid, "state": {}})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not pinned", resp.get_json()["error"])
        latest = self.client.get(
            f"/api/play/attempt/{attempt_id}/checkpoints/latest")
        self.assertEqual(latest.status_code, 404)


if __name__ == "__main__":
    unittest.main()
