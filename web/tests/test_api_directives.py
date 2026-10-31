"""Tests for the JSON directives-panel API (SCRUM-182, SCRUM-183).

Mirrors the /lessons/<id>/directives page behavior through the API:
the React directives panel drives these endpoints with the same pilot
semantics (staff only, real seeded lesson with class-wide and
per-student steers beside a classroom roster). SCRUM-183 adds the
single-directive detail/edit endpoints behind the React edit page.
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


class ApiDirectivesTestCase(unittest.TestCase):
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

    def panel_url(self, lesson_id=None):
        lesson_id = self.ids["lesson_id"] if lesson_id is None else lesson_id
        return f"/api/lessons/{lesson_id}/directives"

    def deactivate_url(self, directive_id):
        return f"/api/directives/{directive_id}/deactivate"

    def detail_url(self, directive_id):
        return f"/api/directives/{directive_id}"

    def edit_url(self, directive_id):
        return f"/api/directives/{directive_id}/edit"

    def _active_directive_id(self):
        self.login("tess")
        panel = self.client.get(self.panel_url()).get_json()["panel"]
        return next(
            row["id"] for row in panel["directives"] if row["active"])

    def test_panel_requires_login_as_json(self):
        resp = self.client.get(self.panel_url())
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())
        resp = self.client.post(self.panel_url(), json={"focus": "x"})
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())
        resp = self.client.post(self.deactivate_url(1))
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())

    def test_directives_forbidden_for_students_as_json(self):
        self.login("sam")
        resp = self.client.get(self.panel_url())
        self.assertEqual(resp.status_code, 403)
        self.assertIn("teachers and admins", resp.get_json()["error"])
        resp = self.client.post(self.panel_url(), json={"focus": "x"})
        self.assertEqual(resp.status_code, 403)
        resp = self.client.post(self.deactivate_url(1))
        self.assertEqual(resp.status_code, 403)

    def test_panel_shows_directives_with_scope_and_roster(self):
        self.login("tess")
        resp = self.client.get(self.panel_url())
        self.assertEqual(resp.status_code, 200)
        panel = resp.get_json()["panel"]
        self.assertEqual(panel["title"], "Volcanoes")
        for key in ("subject", "classroom", "directives", "roster"):
            self.assertIn(key, panel)
        for row in panel["directives"]:
            for key in ("id", "kind", "scope", "focus", "priority",
                        "active"):
                self.assertIn(key, row)
        focuses = [row["focus"] for row in panel["directives"]]
        self.assertIn("Cover the three eruption stages in order.", focuses)
        self.assertIn("Add a labeling challenge for slow readers.", focuses)
        scopes = [row["scope"] for row in panel["directives"]]
        self.assertIn("Class-wide", scopes)
        names = [entry["name"] for entry in panel["roster"]]
        self.assertIn("Sam", names)

    def test_unknown_lesson_is_404_as_json(self):
        self.login("tess")
        resp = self.client.get(self.panel_url(9999))
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Unknown lesson", resp.get_json()["error"])
        resp = self.client.post(self.panel_url(9999),
                                json={"focus": "x"})
        self.assertEqual(resp.status_code, 404)

    def test_unknown_directive_deactivate_is_404_as_json(self):
        self.login("tess")
        resp = self.client.post(self.deactivate_url(9999))
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Unknown directive", resp.get_json()["error"])

    def test_create_class_wide_and_per_student_steers(self):
        self.login("tess")
        resp = self.client.post(
            self.panel_url(),
            json={"focus": "More diagrams.", "priority": "2"})
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["message"], "Directive recorded.")
        wide = [row for row in payload["panel"]["directives"]
                if row["id"] == payload["directive_id"]]
        self.assertEqual(len(wide), 1)
        self.assertEqual(wide[0]["scope"], "Class-wide")
        self.assertEqual(wide[0]["priority"], 2)
        self.assertTrue(wide[0]["active"])
        resp = self.client.post(
            self.panel_url(),
            json={"focus": "Extra time on labels.",
                  "must_include": "big labels",
                  "student_id": str(self.ids["student_id"])})
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["message"], "Directive recorded.")
        personal = [row for row in payload["panel"]["directives"]
                    if row["id"] == payload["directive_id"]]
        self.assertEqual(len(personal), 1)
        self.assertEqual(personal[0]["scope"], "Sam")
        # The panel persists both new steers.
        panel = self.client.get(self.panel_url()).get_json()["panel"]
        focuses = [row["focus"] for row in panel["directives"]]
        self.assertIn("More diagrams.", focuses)
        self.assertIn("Extra time on labels.", focuses)

    def test_create_accepts_json_native_numbers(self):
        self.login("tess")
        resp = self.client.post(
            self.panel_url(),
            json={"focus": "Number-shaped priority still records.",
                  "must_include": ["crater diagram"],
                  "priority": 3,
                  "student_id": None})
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["message"], "Directive recorded.")
        created = [row for row in payload["panel"]["directives"]
                   if row["id"] == payload["directive_id"]]
        self.assertEqual(created[0]["priority"], 3)

    def test_blank_focus_rejected_as_json(self):
        self.login("tess")
        resp = self.client.post(self.panel_url(), json={"focus": "   "})
        self.assertEqual(resp.status_code, 400)
        payload = resp.get_json()
        self.assertEqual(payload["code"], "invalid_directive")
        self.assertIn("invalid_directive", payload["error"])

    def test_deactivate_takes_directive_out_of_active_set(self):
        self.login("tess")
        panel = self.client.get(self.panel_url()).get_json()["panel"]
        target = next(row for row in panel["directives"] if row["active"])
        resp = self.client.post(self.deactivate_url(target["id"]))
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["message"], "Directive deactivated.")
        rows = [row for row in payload["panel"]["directives"]
                if row["id"] == target["id"]]
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["active"])
        # Deactivation is idempotent.
        resp = self.client.post(self.deactivate_url(target["id"]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["message"],
                         "Directive deactivated.")

    def test_admin_may_use_panel(self):
        self.login("ash")
        resp = self.client.get(self.panel_url())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["panel"]["title"], "Volcanoes")
        resp = self.client.post(self.panel_url(),
                                json={"focus": "Admin pacing note."})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["message"], "Directive recorded.")

    def test_detail_and_edit_require_login_as_json(self):
        resp = self.client.get(self.detail_url(1))
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())
        resp = self.client.post(self.edit_url(1), json={"focus": "x"})
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())

    def test_detail_and_edit_forbidden_for_students_as_json(self):
        self.login("sam")
        resp = self.client.get(self.detail_url(1))
        self.assertEqual(resp.status_code, 403)
        self.assertIn("teachers and admins", resp.get_json()["error"])
        resp = self.client.post(self.edit_url(1), json={"focus": "x"})
        self.assertEqual(resp.status_code, 403)

    def test_detail_shows_editable_fields(self):
        target = self._active_directive_id()
        resp = self.client.get(self.detail_url(target))
        self.assertEqual(resp.status_code, 200)
        detail = resp.get_json()["directive"]
        for key in ("id", "lesson_id", "kind", "scope", "focus",
                    "must_include", "must_avoid", "priority", "active"):
            self.assertIn(key, detail)
        self.assertEqual(detail["id"], target)
        self.assertEqual(detail["lesson_id"], self.ids["lesson_id"])
        self.assertIn(detail["kind"], ("steer", "brief"))
        self.assertIn(detail["scope"], ("Class-wide", "Sam"))
        self.assertIsInstance(detail["priority"], int)
        self.assertTrue(detail["active"])

    def test_unknown_directive_detail_and_edit_are_404_as_json(self):
        self.login("tess")
        resp = self.client.get(self.detail_url(9999))
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Unknown directive", resp.get_json()["error"])
        resp = self.client.post(self.edit_url(9999),
                                json={"focus": "x"})
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Unknown directive", resp.get_json()["error"])

    def test_edit_focus_constraints_and_priority(self):
        target = self._active_directive_id()
        resp = self.client.post(
            self.edit_url(target),
            json={"focus": "Edited focus.",
                  "must_include": "crater diagram, ash layers",
                  "must_avoid": "jargon",
                  "priority": "3"})
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["message"], "Directive updated.")
        detail = payload["directive"]
        self.assertEqual(detail["id"], target)
        self.assertEqual(detail["focus"], "Edited focus.")
        self.assertEqual(detail["must_include"], "crater diagram, ash layers")
        self.assertEqual(detail["must_avoid"], "jargon")
        self.assertEqual(detail["priority"], 3)
        # The edit persists and the panel shows the updated values.
        detail = self.client.get(
            self.detail_url(target)).get_json()["directive"]
        self.assertEqual(detail["focus"], "Edited focus.")
        panel = self.client.get(self.panel_url()).get_json()["panel"]
        rows = [row for row in panel["directives"] if row["id"] == target]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["focus"], "Edited focus.")
        self.assertEqual(rows[0]["priority"], 3)

    def test_edit_blank_focus_rejected_as_json(self):
        target = self._active_directive_id()
        before = self.client.get(
            self.detail_url(target)).get_json()["directive"]
        resp = self.client.post(self.edit_url(target),
                                json={"focus": "   "})
        self.assertEqual(resp.status_code, 400)
        payload = resp.get_json()
        self.assertEqual(payload["code"], "invalid_directive")
        self.assertIn("invalid_directive", payload["error"])
        after = self.client.get(
            self.detail_url(target)).get_json()["directive"]
        self.assertEqual(after["focus"], before["focus"])

    def test_edit_accepts_partial_payload(self):
        target = self._active_directive_id()
        before = self.client.get(
            self.detail_url(target)).get_json()["directive"]
        resp = self.client.post(self.edit_url(target),
                                json={"focus": "Focus-only tweak."})
        self.assertEqual(resp.status_code, 200)
        detail = resp.get_json()["directive"]
        self.assertEqual(detail["focus"], "Focus-only tweak.")
        self.assertEqual(detail["priority"], before["priority"])
        self.assertEqual(detail["must_include"], before["must_include"])
        self.assertEqual(detail["must_avoid"], before["must_avoid"])

    def test_edit_accepts_json_native_numbers(self):
        target = self._active_directive_id()
        resp = self.client.post(
            self.edit_url(target),
            json={"focus": "Number-shaped priority edit.",
                  "must_include": ["crater diagram"],
                  "priority": 3})
        self.assertEqual(resp.status_code, 200)
        detail = resp.get_json()["directive"]
        self.assertEqual(detail["priority"], 3)
        self.assertEqual(detail["must_include"], "crater diagram")

    def test_admin_may_edit(self):
        self.login("ash")
        panel = self.client.get(self.panel_url()).get_json()["panel"]
        target = next(
            row["id"] for row in panel["directives"] if row["active"])
        resp = self.client.get(self.detail_url(target))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post(self.edit_url(target),
                                json={"focus": "Admin edit."})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["message"], "Directive updated.")


if __name__ == "__main__":
    unittest.main()
