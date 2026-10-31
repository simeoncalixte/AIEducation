"""Tests for the JSON review-queues API (SCRUM-177).

Mirrors the /review page behavior through /api/review: the React
review queues page drives this endpoint with the same pilot semantics
(staff only, drafts first, low-impact flags inline).
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


class ApiReviewTestCase(unittest.TestCase):
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

    def test_review_requires_login_as_json(self):
        resp = self.client.get("/api/review")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())

    def test_review_forbidden_for_students_as_json(self):
        self.login("sam")
        resp = self.client.get("/api/review")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("teachers and admins", resp.get_json()["error"])

    def test_teacher_queues_cover_all_three_levels(self):
        self.login("tess")
        resp = self.client.get("/api/review")
        self.assertEqual(resp.status_code, 200)
        queues = resp.get_json()["queues"]
        self.assertEqual(set(queues), {"asset", "stage", "lesson"})
        titles = [row["title"] for rows in queues.values()
                  for row in rows]
        for marker in ("Volcano Model", "Eruption", "Volcanoes"):
            self.assertTrue(
                any(marker in title for title in titles),
                f"missing queue marker: {marker}")

    def test_rows_carry_draft_and_live_markers(self):
        self.login("tess")
        queues = self.client.get("/api/review").get_json()["queues"]
        statuses = {row["status"] for rows in queues.values()
                    for row in rows}
        self.assertIn("draft", statuses)
        self.assertIn("published", statuses)
        for rows in queues.values():
            for row in rows:
                self.assertIsInstance(row["id"], int)
                self.assertIsInstance(row["version_no"], int)
                self.assertIn("decision", row)
                self.assertIn("rationale", row)

    def test_drafts_sort_first(self):
        self.login("tess")
        queues = self.client.get("/api/review").get_json()["queues"]
        for rows in queues.values():
            seen_live = False
            for row in rows:
                if row["status"] == "draft":
                    self.assertFalse(
                        seen_live,
                        "draft row sorted after a live row")
                else:
                    seen_live = True

    def test_low_impact_flags_sediment_tray(self):
        self.login("tess")
        queues = self.client.get("/api/review").get_json()["queues"]
        by_title = {row["title"]: row for row in queues["asset"]}
        flagged = [title for title, row in by_title.items()
                   if row["low_impact"]]
        self.assertTrue(
            any("Sediment Tray" in title for title in flagged),
            f"expected a low-impact Sediment Tray row, got: {flagged}")
        self.assertTrue(
            all("Volcano Model" not in title or
                not by_title[title]["low_impact"]
                for title in by_title))

    def test_admin_may_review(self):
        self.login("ash")
        resp = self.client.get("/api/review")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(set(resp.get_json()["queues"]),
                         {"asset", "stage", "lesson"})


if __name__ == "__main__":
    unittest.main()
