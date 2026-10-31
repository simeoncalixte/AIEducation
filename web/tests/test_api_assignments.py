"""Tests for the JSON assignments API (SCRUM-184).

Mirrors the /assignments page behavior through /api/assignments: the
React assignment list drives these endpoints with the same pilot
semantics (staff only, empty state plus lesson/classroom/student
options, exactly-one-target assigns via the shared service).
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


class ApiAssignmentsTestCase(unittest.TestCase):
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

    def _options(self):
        return self.client.get("/api/assignments").get_json()["options"]

    def _assign(self, **overrides):
        options = self._options()
        data = {"lesson_id": str(self.ids["lesson_id"]),
                "classroom_id": str(options["classrooms"][0]["id"]),
                "student_id": ""}
        data.update(overrides)
        return self.client.post("/api/assignments", json=data)

    def test_assignments_requires_login_as_json(self):
        resp = self.client.get("/api/assignments")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())
        resp = self.client.post("/api/assignments",
                                json={"lesson_id": "1"})
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())

    def test_assignments_forbidden_for_students_as_json(self):
        self.login("sam")
        resp = self.client.get("/api/assignments")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("teachers and admins", resp.get_json()["error"])
        resp = self.client.post("/api/assignments",
                                json={"lesson_id": "1"})
        self.assertEqual(resp.status_code, 403)

    def test_list_shows_empty_state_and_form_options(self):
        self.login("tess")
        resp = self.client.get("/api/assignments")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["assignments"], [])
        options = payload["options"]
        for key in ("lessons", "classrooms", "students"):
            self.assertIn(key, options)
        lessons = {row["title"]: row for row in options["lessons"]}
        self.assertIn("Volcanoes", lessons)
        self.assertEqual(lessons["Volcanoes"]["id"],
                         self.ids["lesson_id"])
        self.assertIn("classroom", lessons["Volcanoes"])
        rooms = [row["name"] for row in options["classrooms"]]
        self.assertTrue(any("Room 1" in name for name in rooms))
        students = {row["name"]: row for row in options["students"]}
        self.assertIn("Sam", students)
        self.assertEqual(students["Sam"]["id"], self.ids["student_id"])

    def test_assign_to_classroom_and_student(self):
        self.login("tess")
        resp = self._assign()
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["message"], "Assignment recorded.")
        rows = [row for row in payload["assignments"]
                if row["id"] == payload["assignment_id"]]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["lesson"], "Volcanoes")
        self.assertIn("Room 1", rows[0]["target"])
        self.assertEqual(rows[0]["attempts"], 0)
        for key in ("by",):
            self.assertIn(key, rows[0])
        resp = self._assign(
            classroom_id="",
            student_id=str(self.ids["student_id"]))
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["message"], "Assignment recorded.")
        rows = [row for row in payload["assignments"]
                if row["id"] == payload["assignment_id"]]
        self.assertEqual(rows[0]["target"], "Sam")
        # Both assigns persist in the list.
        rows = self.client.get("/api/assignments").get_json()["assignments"]
        self.assertEqual(len(rows), 2)

    def test_assign_requires_exactly_one_target(self):
        self.login("tess")
        resp = self._assign(classroom_id="", student_id="")
        self.assertEqual(resp.status_code, 400)
        payload = resp.get_json()
        self.assertEqual(payload["code"], "invalid_scope")
        self.assertIn("invalid_scope", payload["error"])
        resp = self._assign(student_id=str(self.ids["student_id"]))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["code"], "invalid_scope")

    def test_assign_accepts_json_native_numbers(self):
        self.login("tess")
        options = self._options()
        resp = self.client.post(
            "/api/assignments",
            json={"lesson_id": self.ids["lesson_id"],
                  "classroom_id": options["classrooms"][0]["id"],
                  "student_id": None})
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["message"], "Assignment recorded.")
        rows = [row for row in payload["assignments"]
                if row["id"] == payload["assignment_id"]]
        self.assertEqual(len(rows), 1)

    def test_unknown_lesson_is_404_as_json(self):
        self.login("tess")
        resp = self._assign(lesson_id="9999")
        self.assertEqual(resp.status_code, 404)
        payload = resp.get_json()
        self.assertEqual(payload["code"], "not_found")
        self.assertIn("not_found", payload["error"])

    def test_repeat_assign_reuses_assignment(self):
        self.login("tess")
        first = self._assign().get_json()["assignment_id"]
        second = self._assign().get_json()["assignment_id"]
        self.assertEqual(first, second)
        rows = self.client.get("/api/assignments").get_json()["assignments"]
        self.assertEqual(len(rows), 1)

    def test_admin_may_use_assignments(self):
        self.login("ash")
        resp = self.client.get("/api/assignments")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["assignments"], [])
        resp = self._assign()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["message"], "Assignment recorded.")


if __name__ == "__main__":
    unittest.main()
