"""Tests for the JSON session/home API (SCRUM-174/175/176).

Mirrors test_auth.py behavior through /api/*: the React shell, login,
and home pages drive these endpoints with the same pilot semantics.
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
from evolvingclass_service import assign_lesson  # noqa: E402
from evolvingclass_web.app import create_app  # noqa: E402
from evolvingclass_web.seed import seed  # noqa: E402


class ApiAuthTestCase(unittest.TestCase):
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
        self.factory = sessionmaker(bind=create_engine(self.url))

    def tearDown(self):
        os.unlink(self._tmp)

    def login(self, login_ref):
        return self.client.post("/api/login", json={"login_ref": login_ref})

    def test_health_ok(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"ok": True})

    def test_session_null_when_logged_out(self):
        resp = self.client.get("/api/session")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"user": None})

    def test_login_choices_list_pilot_users(self):
        resp = self.client.get("/api/login_choices")
        self.assertEqual(resp.status_code, 200)
        users = resp.get_json()["users"]
        by_login = {u["login"]: u for u in users}
        self.assertEqual(by_login["tess"]["role"], "teacher")
        self.assertEqual(by_login["ash"]["role"], "admin")
        self.assertEqual(by_login["sam"]["role"], "student")
        self.assertEqual(by_login["tess"]["name"], "Tess")

    def test_login_lands_with_identity_and_session(self):
        resp = self.login("tess")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["user"]["name"], "Tess")
        self.assertEqual(payload["user"]["role"], "teacher")
        self.assertIn("Logged in as Tess (teacher).",
                      payload["message"])
        resp = self.client.get("/api/session")
        self.assertEqual(resp.get_json()["user"]["name"], "Tess")

    def test_unknown_login_rejected_as_json(self):
        resp = self.login("nobody")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Unknown login", resp.get_json()["error"])
        resp = self.client.get("/api/session")
        self.assertEqual(resp.get_json(), {"user": None})

    def test_logout_clears_session(self):
        self.login("tess")
        resp = self.client.post("/api/logout")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Logged out.", resp.get_json()["message"])
        self.assertEqual(self.client.get("/api/session").get_json(),
                         {"user": None})
        resp = self.client.get("/api/home")
        self.assertEqual(resp.status_code, 401)

    def test_home_requires_login_as_json(self):
        resp = self.client.get("/api/home")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())

    def test_teacher_home_links(self):
        self.login("tess")
        payload = self.client.get("/api/home").get_json()
        labels = [link["label"] for link in payload["links"]]
        self.assertEqual(labels,
                         ["Review queues", "Lessons", "Assignments"])
        hrefs = [link["href"] for link in payload["links"]]
        self.assertEqual(hrefs, ["/review", "/lessons", "/assignments"])
        self.assertNotIn("Audit", labels)

    def test_admin_home_links_include_audit(self):
        self.login("ash")
        payload = self.client.get("/api/home").get_json()
        labels = [link["label"] for link in payload["links"]]
        self.assertIn("Audit", labels)

    def test_student_home_assignments(self):
        self.login("sam")
        payload = self.client.get("/api/home").get_json()
        self.assertEqual(payload["assignments"], [])
        assign_lesson(self.factory, lesson_id=self.ids["lesson_id"],
                      actor_id=self.ids["teacher_id"],
                      classroom_id=self.room_id, student_id=None)
        payload = self.client.get("/api/home").get_json()
        self.assertEqual(len(payload["assignments"]), 1)
        row = payload["assignments"][0]
        self.assertEqual(row["lesson"], "Volcanoes")
        self.assertEqual(row["status"], "not started")
        self.assertEqual(row["attempts"], 0)


if __name__ == "__main__":
    unittest.main()
