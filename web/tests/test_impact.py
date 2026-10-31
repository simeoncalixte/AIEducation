"""Tests for low-impact flags and revise/retire (SCRUM-29)."""

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


class ImpactFlagTestCase(unittest.TestCase):
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

    def test_queue_flags_low_impact_asset(self):
        body = self.client.get("/review").get_data(as_text=True)
        self.assertIn("Sediment Tray", body)
        self.assertIn("Low impact", body)

    def test_dossier_shows_flag_with_evidence(self):
        body = self.client.get(
            f"/review/asset/{self.ids['sediment_live_id']}").get_data(
                as_text=True)
        for marker in ("Low impact", "0.31", "12", "v1", "Room 1",
                       "0.09", "low", "Revise"):
            self.assertIn(marker, body)

    def test_healthy_asset_has_no_flag(self):
        body = self.client.get(
            f"/review/asset/{self.ids['asset_draft_id']}").get_data(
                as_text=True)
        self.assertNotIn("Low impact", body)
        self.assertIn("0.05", body)  # uncertainty shown as evidence

    def test_revise_drafts_new_version_with_lineage(self):
        vid = self.ids["sediment_live_id"]
        body = self.client.post(
            f"/review/asset/{vid}/revise",
            data={"rationale": "coarser grains"},
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("Revision drafted.", body)
        self.assertIn("Revision of v1: coarser grains", body)
        self.assertIn("draft", body)

    def test_revise_draft_rejected(self):
        vid = self.ids["asset_draft_id"]
        body = self.client.post(
            f"/review/asset/{vid}/revise",
            data={"rationale": "nope"},
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("not_published", body)

    def test_retire_audited_and_source_stays(self):
        vid = self.ids["sediment_live_id"]
        body = self.client.post(
            f"/review/asset/{vid}/retire",
            data={"rationale": "replaced"},
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("Retirement recorded.", body)
        self.assertIn("retired", body)
        self.assertIn("replaced", body)


if __name__ == "__main__":
    unittest.main()
