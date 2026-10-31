"""Tests for the teacher brief flow (SCRUM-15)."""

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


class BriefTestCase(unittest.TestCase):
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

    def test_lessons_list_shows_lesson_with_brief_link(self):
        resp = self.client.get("/lessons")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        self.assertIn("Volcanoes", body)
        self.assertIn(f"/lessons/{self.ids['lesson_id']}/brief", body)

    def test_brief_form_shows_fields_and_active_directives(self):
        resp = self.client.get(
            f"/lessons/{self.ids['lesson_id']}/brief")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        for marker in ("Volcanoes", "Objectives", "Mental models",
                       "Focus", "Must-include", "Must-avoid",
                       "Cover the three eruption stages"):
            self.assertIn(marker, body)

    def test_unknown_lesson_brief_is_404(self):
        self.assertEqual(
            self.client.get("/lessons/9999/brief").status_code, 404)
        self.assertEqual(
            self.client.post("/lessons/9999/brief",
                             data={"focus": "x"}).status_code, 404)

    def test_submit_brief_lands_on_draft_with_rationale_and_snapshot(self):
        resp = self.client.post(
            f"/lessons/{self.ids['lesson_id']}/brief",
            data={
                "objectives": "sci.eruptions\nsci.rocks",
                "mental_models": "Magma rises through a vent.",
                "focus": "Drill the chamber-to-surface path.",
                "must_include": "crater diagram",
                "must_avoid": "scary eruption footage",
                "priority": "2",
            },
            follow_redirects=True)
        body = resp.get_data(as_text=True)
        self.assertIn("Brief recorded.", body)
        self.assertIn("Drill the chamber-to-surface path.", body)
        self.assertIn("Directive coverage", body)
        self.assertIn("brief-composer", body)
        # The draft joins the lesson review queue.
        queue = self.client.get("/review").get_data(as_text=True)
        self.assertIn("Drill the chamber-to-surface path.", queue)

    def test_blank_focus_rejected(self):
        resp = self.client.post(
            f"/lessons/{self.ids['lesson_id']}/brief",
            data={"focus": "   "},
            follow_redirects=True)
        self.assertIn("invalid_brief", resp.get_data(as_text=True))

    def test_actor_gate_redirects_for_brief_pages(self):
        with self.client.session_transaction() as sess:
            sess.pop("actor_id", None)
        resp = self.client.get("/lessons")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])
        resp = self.client.get(
            f"/lessons/{self.ids['lesson_id']}/brief")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])


if __name__ == "__main__":
    unittest.main()
