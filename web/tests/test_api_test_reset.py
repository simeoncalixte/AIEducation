"""Tests for the test-only database reset endpoint.

POST /api/__test__/reset exists solely for the live Storybook
interaction suite (test-live.sh): it restores the seeded demo data so
each story runs order-independently. The route is registered only when
ALLOW_TEST_RESET=1 and refuses non-sqlite databases.
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


class ApiTestResetTestCase(unittest.TestCase):
    def setUp(self):
        self._old_flag = os.environ.get("ALLOW_TEST_RESET")
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self._tmp = tmp.name
        self.url = f"sqlite:///{tmp.name}"
        self.ids = seed(self.url)

    def tearDown(self):
        if self._old_flag is None:
            os.environ.pop("ALLOW_TEST_RESET", None)
        else:
            os.environ["ALLOW_TEST_RESET"] = self._old_flag
        os.unlink(self._tmp)

    def make_client(self, url=None):
        app = create_app(url or self.url)
        app.config["TESTING"] = True
        return app.test_client()

    def panel_url(self):
        return f"/api/lessons/{self.ids['lesson_id']}/directives"

    def test_reset_missing_without_flag(self):
        os.environ.pop("ALLOW_TEST_RESET", None)
        client = self.make_client()
        client.post("/api/login", json={"login_ref": "tess"})
        resp = client.post("/api/__test__/reset")
        self.assertEqual(resp.status_code, 404)

    def test_reset_restores_seeded_state(self):
        os.environ["ALLOW_TEST_RESET"] = "1"
        client = self.make_client()
        client.post("/api/login", json={"login_ref": "tess"})
        resp = client.post(self.panel_url(), json={"focus": "Reset probe."})
        self.assertEqual(resp.status_code, 200)

        fresh = self.make_client()
        resp = fresh.post("/api/__test__/reset")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])

        fresh.post("/api/login", json={"login_ref": "tess"})
        resp = fresh.get(self.panel_url())
        self.assertEqual(resp.status_code, 200)
        focuses = [row["focus"]
                   for row in resp.get_json()["panel"]["directives"]]
        self.assertNotIn("Reset probe.", focuses)
        self.assertIn("Cover the three eruption stages in order.", focuses)

    def test_reset_refuses_non_sqlite(self):
        os.environ["ALLOW_TEST_RESET"] = "1"
        client = self.make_client("postgresql://localhost/no-such-db")
        resp = client.post("/api/__test__/reset")
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
