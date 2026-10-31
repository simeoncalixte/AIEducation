"""Tests for the app shell: login, roles, guards (SCRUM-122)."""

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


class AuthShellTestCase(unittest.TestCase):
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
        return self.client.post("/login", data={"login_ref": login_ref},
                               follow_redirects=True)

    def test_login_page_lists_pilot_users(self):
        body = self.client.get("/login").get_data(as_text=True)
        for marker in ("tess", "ash", "sam", "teacher", "admin",
                       "student"):
            self.assertIn(marker, body)

    def test_teacher_login_lands_home_with_review_nav(self):
        body = self.login("tess").get_data(as_text=True)
        self.assertIn("Logged in as Tess (teacher).", body)
        self.assertIn("Review queues", body)
        self.assertIn("Tess (teacher)", body)
        self.assertEqual(self.client.get("/review").status_code, 200)

    def test_admin_login_reaches_review(self):
        body = self.login("ash").get_data(as_text=True)
        self.assertIn("Logged in as Ash (admin).", body)
        self.assertEqual(self.client.get("/review").status_code, 200)

    def test_student_login_sees_home_but_not_review(self):
        body = self.login("sam").get_data(as_text=True)
        self.assertIn("My assignments", body)
        self.assertIn("No assignments yet.", body)
        resp = self.client.get("/review")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("teachers and admins",
                      resp.get_data(as_text=True))

    def test_unknown_login_rejected(self):
        body = self.login("nobody").get_data(as_text=True)
        self.assertIn("Unknown login", body)

    def test_logout_clears_session(self):
        self.login("tess")
        body = self.client.get("/logout",
                               follow_redirects=True).get_data(as_text=True)
        self.assertIn("Logged out.", body)
        resp = self.client.get("/review")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_logged_out_redirects_to_login(self):
        resp = self.client.get("/lessons")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_missing_page_renders_error(self):
        self.login("tess")
        resp = self.client.get("/no-such-page")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("does not exist", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
