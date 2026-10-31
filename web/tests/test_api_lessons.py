"""Tests for the JSON lesson-list API (SCRUM-180).

Mirrors the /lessons page behavior through /api/lessons: the React
lesson list page drives this endpoint with the same pilot semantics
(staff only, real seeded lessons with draft/published counts).
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


class ApiLessonsTestCase(unittest.TestCase):
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

    def test_lessons_requires_login_as_json(self):
        resp = self.client.get("/api/lessons")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())

    def test_lessons_forbidden_for_students_as_json(self):
        self.login("sam")
        resp = self.client.get("/api/lessons")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("teachers and admins", resp.get_json()["error"])

    def test_teacher_sees_seeded_lesson_with_counts(self):
        self.login("tess")
        resp = self.client.get("/api/lessons")
        self.assertEqual(resp.status_code, 200)
        lessons = resp.get_json()["lessons"]
        by_title = {row["title"]: row for row in lessons}
        self.assertIn("Volcanoes", by_title)
        row = by_title["Volcanoes"]
        self.assertEqual(row["id"], self.ids["lesson_id"])
        for key in ("subject", "classroom", "drafts", "published"):
            self.assertIn(key, row)
        self.assertIsInstance(row["drafts"], int)
        self.assertIsInstance(row["published"], int)

    def test_list_shows_only_real_lessons(self):
        self.login("tess")
        lessons = self.client.get("/api/lessons").get_json()["lessons"]
        ids = {row["id"] for row in lessons}
        self.assertIn(self.ids["lesson_id"], ids)
        self.assertNotIn(9999, ids)

    def test_admin_may_list_lessons(self):
        self.login("ash")
        resp = self.client.get("/api/lessons")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            any(row["title"] == "Volcanoes"
                for row in resp.get_json()["lessons"]))


if __name__ == "__main__":
    unittest.main()
