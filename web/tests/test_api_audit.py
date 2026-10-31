"""Tests for the JSON admin-audit API (SCRUM-189).

Mirrors the /audit page behavior through /api/audit: the React
audit page drives this endpoint with the same pilot semantics
(admin only, cross-classroom lesson status, actor/date filters).
Date bounds use fixed far-past/far-future values so the suite is
independent of the local/UTC date skew.
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

from evolvingclass_web.app import create_app  # noqa: E402
from evolvingclass_web.seed import seed  # noqa: E402


class ApiAuditTestCase(unittest.TestCase):
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

    def test_audit_requires_login_as_json(self):
        resp = self.client.get("/api/audit")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())

    def test_audit_forbidden_for_teacher_as_json(self):
        self.login("tess")
        resp = self.client.get("/api/audit")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("school admins", resp.get_json()["error"])

    def test_audit_forbidden_for_student_as_json(self):
        self.login("sam")
        resp = self.client.get("/api/audit")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("school admins", resp.get_json()["error"])

    def test_admin_sees_status_trail_and_actors(self):
        self.login("ash")
        resp = self.client.get("/api/audit")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        rooms = {room["name"]: room for room in payload["status"]}
        self.assertIn("Room 1", rooms)
        lessons = {row["title"]: row
                   for row in rooms["Room 1"]["lessons"]}
        self.assertIn("Volcanoes", lessons)
        row = lessons["Volcanoes"]
        for key in ("subject", "drafts", "published", "retired",
                    "assignments", "attempts"):
            self.assertIn(key, row)
        self.assertIsInstance(row["drafts"], int)
        self.assertIsInstance(row["published"], int)
        results = {entry["result"] for entry in payload["trail"]}
        self.assertIn("approved", results)
        self.assertIn("published", results)
        entry = payload["trail"][0]
        for key in ("at_text", "actor_id", "actor", "kind", "result",
                    "target", "rationale"):
            self.assertIn(key, entry)
        self.assertTrue(any("Volcano Model v1" in entry["target"]
                            for entry in payload["trail"]))
        actors = {user["name"]: user for user in payload["actors"]}
        self.assertIn("Tess", actors)
        self.assertEqual(actors["Tess"]["role"], "teacher")

    def test_actor_filter(self):
        self.login("ash")
        teacher = self.client.get(
            f"/api/audit?actor={self.ids['teacher_id']}").get_json()
        self.assertTrue(
            all(entry["actor_id"] == self.ids["teacher_id"]
                for entry in teacher["trail"]))
        self.assertTrue(
            any(entry["result"] == "approved"
                for entry in teacher["trail"]))
        self.assertEqual(teacher["filters"]["actor"],
                         self.ids["teacher_id"])
        student = self.client.get(
            f"/api/audit?actor={self.ids['student_id']}").get_json()
        self.assertEqual(student["trail"], [])

    def test_date_filters(self):
        self.login("ash")
        wide = self.client.get("/api/audit?since=2000-01-01").get_json()
        self.assertTrue(
            any(entry["result"] == "approved" for entry in wide["trail"]))
        self.assertEqual(wide["filters"]["since"], "2000-01-01")
        future = self.client.get("/api/audit?since=2100-01-01").get_json()
        self.assertEqual(future["trail"], [])
        past = self.client.get("/api/audit?until=2000-01-01").get_json()
        self.assertEqual(past["trail"], [])
        self.assertEqual(past["filters"]["until"], "2000-01-01")
        invalid = self.client.get("/api/audit?since=not-a-date").get_json()
        self.assertTrue(
            any(entry["result"] == "approved" for entry in invalid["trail"]))
        self.assertIsNone(invalid["filters"]["since"])


if __name__ == "__main__":
    unittest.main()
