"""Tests for the directives panel and scoped briefs (SCRUM-123, SCRUM-17)."""

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

from DataModels import Directive  # noqa: E402
from evolvingclass_web.app import create_app  # noqa: E402
from evolvingclass_web.seed import seed  # noqa: E402


class DirectivesTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self._tmp = tmp.name
        self.url = f"sqlite:///{tmp.name}"
        self.ids = seed(self.url)
        self.app = create_app(self.url)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["actor_id"] = self.ids["teacher_id"]

    def tearDown(self):
        os.unlink(self._tmp)

    def _panel(self):
        return self.client.get(
            f"/lessons/{self.ids['lesson_id']}/directives")

    def _first_directive_id(self):
        engine = create_engine(self.url)
        try:
            with engine.connect() as conn:
                return conn.execute(
                    select(Directive.id).order_by(
                        Directive.id).limit(1)).scalar_one()
        finally:
            engine.dispose()

    def test_panel_lists_directives_with_scope_and_roster(self):
        body = self._panel().get_data(as_text=True)
        for marker in ("Class-wide", "brief", "steer",
                       "Cover the three eruption stages",
                       "Add a labeling challenge",
                       "Sam", "Deactivate", "Edit"):
            self.assertIn(marker, body)

    def test_unknown_lesson_panel_is_404(self):
        self.assertEqual(
            self.client.get("/lessons/9999/directives").status_code, 404)

    def test_create_class_wide_and_per_student_steers(self):
        base = f"/lessons/{self.ids['lesson_id']}/directives"
        body = self.client.post(
            base, data={"focus": "More diagrams."},
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("Directive recorded.", body)
        self.assertIn("More diagrams.", body)
        body = self.client.post(
            base, data={"focus": "Extra time on labels.",
                        "student_id": str(self.ids["student_id"])},
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("Directive recorded.", body)
        self.assertIn("Extra time on labels.", body)
        self.assertIn("Sam", body)

    def test_blank_focus_rejected(self):
        body = self.client.post(
            f"/lessons/{self.ids['lesson_id']}/directives",
            data={"focus": "  "},
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("invalid_directive", body)

    def test_edit_and_deactivate(self):
        did = self._first_directive_id()
        self.assertEqual(
            self.client.get(f"/directives/{did}/edit").status_code, 200)
        body = self.client.post(
            f"/directives/{did}/edit",
            data={"focus": "Edited focus.", "priority": "3"},
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("Directive updated.", body)
        self.assertIn("Edited focus.", body)
        body = self.client.post(
            f"/directives/{did}/deactivate",
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("Directive deactivated.", body)
        self.assertIn("Edited focus.", body)
        self.assertEqual(
            self.client.get("/directives/9999/edit").status_code, 404)

    def test_brief_with_student_scope_drafts_personal_variant(self):
        body = self.client.post(
            f"/lessons/{self.ids['lesson_id']}/brief",
            data={"focus": "Gentler eruption pacing.",
                  "student_id": str(self.ids["student_id"])},
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("Brief recorded.", body)
        self.assertIn("personal: Sam", body)
        self.assertIn("Directive coverage", body)
        self.assertIn("Gentler eruption pacing.", body)

    def test_student_cannot_open_panel(self):
        with self.client.session_transaction() as sess:
            sess["actor_id"] = self.ids["student_id"]
        self.assertEqual(self._panel().status_code, 403)


if __name__ == "__main__":
    unittest.main()
