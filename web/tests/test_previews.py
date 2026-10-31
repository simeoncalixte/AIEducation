"""Tests for publish-time preview finalization (SCRUM-28)."""

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

from DataModels import PreviewArtifact  # noqa: E402
from evolvingclass_web.app import create_app  # noqa: E402
from evolvingclass_web.seed import seed  # noqa: E402


class PreviewTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self._tmp = tmp.name
        self.url = f"sqlite:///{tmp.name}"
        self.ids = seed(self.url)
        self.app = create_app(self.url)
        self.app.config["TESTING"] = True
        self._previews = tempfile.TemporaryDirectory()
        self.app.config["preview_dir"] = self._previews.name
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["actor_id"] = self.ids["teacher_id"]

    def tearDown(self):
        self._previews.cleanup()
        os.unlink(self._tmp)

    def _artifacts(self, kind, version_id):
        engine = create_engine(self.url)
        try:
            with engine.connect() as conn:
                rows = list(conn.execute(
                    PreviewArtifact.__table__.select().where(
                        getattr(PreviewArtifact,
                                f"{kind}_version_id") == version_id)))
                return [dict(r._mapping) for r in rows]
        finally:
            engine.dispose()

    def test_publish_asset_finalizes_and_shows_preview(self):
        vid = self.ids["asset_draft_id"]
        self.client.post(f"/review/asset/{vid}/approve",
                         data={"rationale": "good"})
        body = self.client.post(
            f"/review/asset/{vid}/publish", data={"rationale": "ship"},
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("Previews", body)
        self.assertIn("v2_poster.svg", body)
        rows = self._artifacts("asset", vid)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "poster")
        self.assertTrue(os.path.exists(
            os.path.join(self._previews.name, rows[0]["storage_ref"])))

    def test_publish_stage_finalizes_namespaced_preview(self):
        for vid in (self.ids["asset_draft_id"],
                    self.ids["challenge_draft_id"]):
            self.client.post(f"/review/asset/{vid}/approve",
                             data={"rationale": "ok"})
            self.client.post(f"/review/asset/{vid}/publish",
                             data={"rationale": "ship"})
        vid = self.ids["stage_draft_id"]
        self.client.post(f"/review/stage/{vid}/approve",
                         data={"rationale": "ok"})
        body = self.client.post(
            f"/review/stage/{vid}/publish", data={"rationale": "ship"},
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("Previews", body)
        self.assertIn("stage/", body)
        rows = self._artifacts("stage", vid)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["storage_ref"].startswith("stage/"))

    def test_publish_without_preview_dir_skips_preview(self):
        self.app.config["preview_dir"] = None
        vid = self.ids["asset_draft_id"]
        self.client.post(f"/review/asset/{vid}/approve",
                         data={"rationale": "good"})
        body = self.client.post(
            f"/review/asset/{vid}/publish", data={"rationale": "ship"},
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("Publication recorded.", body)
        self.assertIn("No previews rendered for this version yet.", body)
        self.assertEqual(self._artifacts("asset", vid), [])


if __name__ == "__main__":
    unittest.main()
