"""Tests for the JSON brief-composer API (SCRUM-181).

Mirrors the /lessons/<id>/brief page behavior through the API: the
React brief composer drives these endpoints with the same pilot
semantics (staff only, real seeded lesson with active directives and
a classroom roster).
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


class ApiBriefTestCase(unittest.TestCase):
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

    def brief_url(self, lesson_id=None):
        lesson_id = self.ids["lesson_id"] if lesson_id is None else lesson_id
        return f"/api/lessons/{lesson_id}/brief"

    def test_context_requires_login_as_json(self):
        resp = self.client.get(self.brief_url())
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())
        resp = self.client.post(self.brief_url(), json={"focus": "x"})
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())

    def test_brief_forbidden_for_students_as_json(self):
        self.login("sam")
        resp = self.client.get(self.brief_url())
        self.assertEqual(resp.status_code, 403)
        self.assertIn("teachers and admins", resp.get_json()["error"])
        resp = self.client.post(self.brief_url(), json={"focus": "x"})
        self.assertEqual(resp.status_code, 403)

    def test_context_shows_lesson_directives_and_roster(self):
        self.login("tess")
        resp = self.client.get(self.brief_url())
        self.assertEqual(resp.status_code, 200)
        brief = resp.get_json()["brief"]
        self.assertEqual(brief["title"], "Volcanoes")
        for key in ("subject", "classroom", "directives", "roster"):
            self.assertIn(key, brief)
        focuses = [row["focus"] for row in brief["directives"]]
        self.assertIn("Cover the three eruption stages in order.", focuses)
        for row in brief["directives"]:
            for key in ("id", "kind", "scope", "focus", "priority",
                        "active"):
                self.assertIn(key, row)
        names = [entry["name"] for entry in brief["roster"]]
        self.assertIn("Sam", names)

    def test_unknown_lesson_is_404_as_json(self):
        self.login("tess")
        resp = self.client.get(self.brief_url(9999))
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Unknown lesson", resp.get_json()["error"])
        resp = self.client.post(self.brief_url(9999),
                                json={"focus": "x"})
        self.assertEqual(resp.status_code, 404)

    def test_submit_persists_and_returns_draft_dossier(self):
        self.login("tess")
        resp = self.client.post(
            self.brief_url(),
            json={
                "objectives": "sci.eruptions\nsci.rocks",
                "mental_models": "Magma rises through a vent.",
                "focus": "Drill the chamber-to-surface path.",
                "must_include": "crater diagram",
                "must_avoid": "scary eruption footage",
                "priority": "2",
                "student_id": "",
            })
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["message"], "Brief recorded.")
        dossier = payload["dossier"]
        self.assertEqual(dossier["id"], payload["version_id"])
        self.assertEqual(dossier["kind"], "lesson")
        self.assertEqual(dossier["status"], "draft")
        self.assertIn("Drill the chamber-to-surface path.",
                      dossier["rationale"])
        coverage = dossier["coverage"]
        self.assertTrue(coverage["snapshot_present"])
        self.assertIn("Drill the chamber-to-surface path.",
                      coverage["brief"])
        self.assertTrue(any(
            row["focus"] == "Drill the chamber-to-surface path."
            for row in coverage["snapshot_directives"]))
        # The draft joins the lesson review queue.
        queues = self.client.get("/api/review").get_json()["queues"]
        rationales = " ".join(row["rationale"] for row in queues["lesson"])
        self.assertIn("Drill the chamber-to-surface path.", rationales)

    def test_submit_accepts_json_native_lists_and_numbers(self):
        self.login("tess")
        resp = self.client.post(
            self.brief_url(),
            json={
                "objectives": ["sci.eruptions", "", "sci.rocks"],
                "focus": "List-shaped objectives still draft.",
                "must_include": ["crater diagram"],
                "priority": 2,
                "student_id": None,
            })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["message"], "Brief recorded.")

    def test_blank_focus_rejected_as_json(self):
        self.login("tess")
        resp = self.client.post(self.brief_url(), json={"focus": "   "})
        self.assertEqual(resp.status_code, 400)
        payload = resp.get_json()
        self.assertEqual(payload["code"], "invalid_brief")
        self.assertIn("invalid_brief", payload["error"])

    def test_admin_may_brief(self):
        self.login("ash")
        resp = self.client.get(self.brief_url())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["brief"]["title"], "Volcanoes")
        resp = self.client.post(self.brief_url(),
                                json={"focus": "Admin pacing note."})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["message"], "Brief recorded.")


if __name__ == "__main__":
    unittest.main()
