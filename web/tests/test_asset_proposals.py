"""Tests for asset proposals with reuse data (SCRUM-27)."""

import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "database"))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "service"))
sys.path.insert(0, os.path.join(ROOT, "web"))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from DataModels import AssetUse  # noqa: E402
from evolvingclass_web.app import create_app  # noqa: E402
from evolvingclass_web.seed import seed  # noqa: E402


class AssetProposalTestCase(unittest.TestCase):
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

    def test_asset_detail_shows_usage_refs(self):
        resp = self.client.get(
            f"/review/asset/{self.ids['asset_draft_id']}")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        for marker in ("Used in", "Volcanoes / Eruption", "stage",
                       "centerpiece", "draft"):
            self.assertIn(marker, body)

    def test_unused_version_shows_empty_usage(self):
        resp = self.client.get(
            f"/review/asset/{self.ids['challenge_draft_id']}")
        body = resp.get_data(as_text=True)
        # The challenge draft is used by the stage draft as a challenge.
        self.assertIn("Used in", body)
        self.assertIn("challenge", body)

    def test_usage_refs_cover_lesson_and_challenge_consumers(self):
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        with factory() as session, session.begin():
            session.add(AssetUse(
                asset_version_id=self.ids["asset_draft_id"],
                lesson_version_id=self.ids["lesson_draft_id"],
                position=1, role="reading", param_overrides={}))
            session.add(AssetUse(
                asset_version_id=self.ids["asset_draft_id"],
                challenge_version_id=self.ids["challenge_draft_id"],
                position=2, role="figure", param_overrides={}))
        engine.dispose()
        body = self.client.get(
            f"/review/asset/{self.ids['asset_draft_id']}").get_data(
                as_text=True)
        for marker in ("Volcanoes", "lesson", "reading",
                       "Label the Parts", "challenge", "figure"):
            self.assertIn(marker, body)

    def test_approve_edit_reject_record_rationale(self):
        vid = self.ids["challenge_draft_id"]
        self.client.post(f"/review/asset/{vid}/reject",
                         data={"rationale": "too hard for now"})
        self.client.post(f"/review/asset/{vid}/approve",
                         data={"rationale": "softened difficulty"})
        body = self.client.post(
            f"/review/asset/{vid}/edit",
            data={"rationale": "Label v2 note."},
            follow_redirects=True).get_data(as_text=True)
        for marker in ("too hard for now", "softened difficulty",
                       "Label v2 note."):
            self.assertIn(marker, body)


if __name__ == "__main__":
    unittest.main()
