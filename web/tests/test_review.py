"""Tests for the teacher review queues (SCRUM-124)."""

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


class ReviewTestCase(unittest.TestCase):
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

    # -- queues and dossiers ------------------------------------------

    def test_queues_show_all_three_levels(self):
        resp = self.client.get("/review")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        for marker in ("Volcano Model", "Eruption", "Volcanoes",
                       "Asset proposals", "Stage proposals",
                       "Lesson proposals"):
            self.assertIn(marker, body)

    def test_asset_detail_shows_diff_coverage_reuse_impact(self):
        resp = self.client.get(
            f"/review/asset/{self.ids['asset_draft_id']}")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        for marker in ("What changed", "vs v1", "content_ref",
                       "Directive coverage", "Cover the three eruption",
                       "Reuse matches", "Rock Samples",
                       "Impact scores", "0.72"):
            self.assertIn(marker, body)

    def test_stage_detail_shows_uses_with_impact(self):
        resp = self.client.get(
            f"/review/stage/{self.ids['stage_draft_id']}")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        for marker in ("Asset uses", "Volcano Model", "Label the Parts",
                       "challenge"):
            self.assertIn(marker, body)

    def test_lesson_detail_shows_composition_and_audit(self):
        resp = self.client.get(
            f"/review/lesson/{self.ids['lesson_live_id']}")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        for marker in ("Stage composition", "Eruption",
                       "Audit trail", "published", "Live."):
            self.assertIn(marker, body)

    def test_actor_gate_redirects_without_reviewer(self):
        with self.client.session_transaction() as sess:
            sess.pop("actor_id", None)
        resp = self.client.get("/review")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])
        self.assertEqual(self.client.get("/login").status_code, 200)

    # -- actions --------------------------------------------------------

    def test_approve_then_publish_asset(self):
        vid = self.ids["asset_draft_id"]
        resp = self.client.post(f"/review/asset/{vid}/approve",
                                data={"rationale": "good"},
                                follow_redirects=True)
        self.assertIn("Approval recorded.", resp.get_data(as_text=True))
        resp = self.client.post(f"/review/asset/{vid}/publish",
                                data={"rationale": "ship"},
                                follow_redirects=True)
        body = resp.get_data(as_text=True)
        self.assertIn("Publication recorded.", body)
        self.assertIn("published", body)

    def test_reject_records_decision(self):
        vid = self.ids["challenge_draft_id"]
        resp = self.client.post(f"/review/asset/{vid}/reject",
                                data={"rationale": "too hard"},
                                follow_redirects=True)
        body = resp.get_data(as_text=True)
        self.assertIn("Rejection recorded.", body)
        self.assertIn("rejected", body)

    def test_publish_blocked_by_draft_dependency(self):
        vid = self.ids["stage_draft_id"]
        self.client.post(f"/review/stage/{vid}/approve",
                         data={"rationale": "ok"})
        resp = self.client.post(f"/review/stage/{vid}/publish",
                                data={"rationale": "ship"},
                                follow_redirects=True)
        self.assertIn("unpublished_dependency",
                      resp.get_data(as_text=True))

    def test_edit_updates_rationale(self):
        vid = self.ids["lesson_draft_id"]
        self.assertEqual(
            self.client.get(f"/review/lesson/{vid}/edit").status_code, 200)
        resp = self.client.post(
            f"/review/lesson/{vid}/edit",
            data={"rationale": "Revised pacing note."},
            follow_redirects=True)
        self.assertIn("Revised pacing note.", resp.get_data(as_text=True))

    def test_edit_non_draft_rejected(self):
        vid = self.ids["lesson_live_id"]
        resp = self.client.post(
            f"/review/lesson/{vid}/edit",
            data={"rationale": "too late"},
            follow_redirects=True)
        self.assertIn("not_draft", resp.get_data(as_text=True))

    def test_rollback_restores_retired_lesson(self):
        vid = self.ids["lesson_retired_id"]
        resp = self.client.post(f"/review/lesson/{vid}/rollback",
                                data={"rationale": "v2 pacing off"},
                                follow_redirects=True)
        body = resp.get_data(as_text=True)
        self.assertIn("Rollback recorded.", body)
        self.assertIn("rolled_back", body)

    def test_retire_live_lesson(self):
        vid = self.ids["lesson_live_id"]
        resp = self.client.post(f"/review/lesson/{vid}/retire",
                                data={"rationale": "done"},
                                follow_redirects=True)
        body = resp.get_data(as_text=True)
        self.assertIn("Retirement recorded.", body)
        self.assertIn("retired", body)


if __name__ == "__main__":
    unittest.main()
