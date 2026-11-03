"""Tests for the launch matching API (SCRUM-39).

POST /api/play/attempt/<id>/launch checks scene requirements
against reported device capabilities and logs the routing decision;
GET .../launch reads the per-launch log. Owner-only writes with
teacher read-only preview, mirroring the other attempt routes.
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


class ApiLaunchTestCase(unittest.TestCase):
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

    def _require(self, stage_version_id, capability, required):
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        with factory() as session, session.begin():
            session.add(m.SceneRequirement(
                stage_version_id=stage_version_id,
                capability=capability, required=required))
        engine.dispose()

    def _device(self, capabilities):
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        with factory() as session, session.begin():
            student_id = session.scalar(
                select(m.AppUser.id).where(
                    m.AppUser.login_ref == "sam"))
            device = m.Device(student_id=student_id, label="Quest 3")
            session.add(device)
            session.flush()
            for capability in capabilities:
                session.add(m.DeviceCapability(
                    device_id=device.id, capability=capability))
            device_id = device.id
        engine.dispose()
        return device_id

    def _launch(self, attempt_id, vid, capabilities=None, device_id=None):
        body = {"stage_version_id": vid}
        if capabilities is not None:
            body["capabilities"] = capabilities
        if device_id is not None:
            body["device_id"] = device_id
        return self.client.post(
            f"/api/play/attempt/{attempt_id}/launch", json=body)

    def test_launch_requires_login_as_json(self):
        resp = self.client.post("/api/play/attempt/1/launch", json={})
        self.assertEqual(resp.status_code, 401)
        resp = self.client.get("/api/play/attempt/1/launch")
        self.assertEqual(resp.status_code, 401)

    def test_launch_routes_and_logs_decision(self):
        attempt_id = self._attempt()
        vid = self._pinned_stage_version(attempt_id)
        self._require(vid, "webxr", True)
        resp = self._launch(attempt_id, vid, ["webxr"])
        self.assertEqual(resp.status_code, 200)
        decision = resp.get_json()
        self.assertEqual(decision["route"], "immersive")
        self.assertEqual(decision["missing_required"], [])
        history = self.client.get(
            f"/api/play/attempt/{attempt_id}/launch").get_json()
        self.assertFalse(history["preview"])
        self.assertEqual(len(history["launches"]), 1)
        self.assertEqual(history["launches"][0]["route"], "immersive")
        self.assertEqual(history["launches"][0]["stage_version_id"], vid)

    def test_launch_falls_back_on_missing_requirement(self):
        attempt_id = self._attempt()
        vid = self._pinned_stage_version(attempt_id)
        self._require(vid, "webxr", True)
        resp = self._launch(attempt_id, vid, ["gamepad"])
        self.assertEqual(resp.status_code, 200)
        decision = resp.get_json()
        self.assertEqual(decision["route"], "web")
        self.assertEqual(decision["missing_required"], ["webxr"])
        self.assertIn("webxr", decision["reason"])

    def test_launch_reads_reported_device_capabilities(self):
        attempt_id = self._attempt()
        vid = self._pinned_stage_version(attempt_id)
        self._require(vid, "webxr", True)
        device_id = self._device(["webxr"])
        resp = self._launch(attempt_id, vid, device_id=device_id)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["route"], "immersive")
        self.assertEqual(resp.get_json()["device_id"], device_id)

    def test_unknown_attempt_is_404_as_json(self):
        attempt_id = self._attempt()
        vid = self._pinned_stage_version(attempt_id)
        resp = self._launch(4242, vid, ["webxr"])
        self.assertEqual(resp.status_code, 404)
        resp = self.client.get("/api/play/attempt/4242/launch")
        self.assertEqual(resp.status_code, 404)

    def test_attempt_isolation_between_students(self):
        attempt_id = self._attempt()
        vid = self._pinned_stage_version(attempt_id)
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
        resp = self._launch(attempt_id, vid, ["webxr"])
        self.assertEqual(resp.status_code, 403)
        resp = self.client.get(f"/api/play/attempt/{attempt_id}/launch")
        self.assertEqual(resp.status_code, 403)

    def test_teacher_preview_read_only(self):
        attempt_id = self._attempt()
        vid = self._pinned_stage_version(attempt_id)
        self._launch(attempt_id, vid, ["webxr"])
        self.login("tess")
        resp = self.client.get(f"/api/play/attempt/{attempt_id}/launch")
        self.assertEqual(resp.status_code, 200)
        found = resp.get_json()
        self.assertTrue(found["preview"])
        self.assertEqual(len(found["launches"]), 1)
        resp = self._launch(attempt_id, vid, ["webxr"])
        self.assertEqual(resp.status_code, 403)

    def test_invalid_shapes_rejected_as_json(self):
        attempt_id = self._attempt()
        vid = self._pinned_stage_version(attempt_id)
        for body, marker in [
            ({"capabilities": ["webxr"]}, "stage_version_id"),
            ({"stage_version_id": "x", "capabilities": ["webxr"]},
             "stage_version_id"),
            ({"stage_version_id": vid, "capabilities": "webxr"},
             "capabilities"),
            ({"stage_version_id": vid, "capabilities": ["  "]},
             "capabilities"),
            ({"stage_version_id": vid}, "capabilities"),
            ({"stage_version_id": vid, "capabilities": ["webxr"],
              "device_id": "x"}, "device_id"),
        ]:
            resp = self.client.post(
                f"/api/play/attempt/{attempt_id}/launch", json=body)
            self.assertEqual(resp.status_code, 400, body)
            self.assertIn(marker, resp.get_json()["error"])

    def test_unpinned_and_unknown_stage_versions_rejected(self):
        attempt_id = self._attempt()
        resp = self._launch(attempt_id, 4242, ["webxr"])
        self.assertEqual(resp.status_code, 404)
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        with factory() as session, session.begin():
            stage_id = session.scalar(select(m.Stage.id))
            spare = m.StageVersion(
                stage_id=stage_id, version_no=99,
                status=m.VersionStatus.published, rationale="r")
            session.add(spare)
            session.flush()
            spare_id = spare.id
        engine.dispose()
        resp = self._launch(attempt_id, spare_id, ["webxr"])
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not pinned", resp.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
