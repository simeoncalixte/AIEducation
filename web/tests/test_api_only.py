"""The Flask app serves the JSON API only; React owns every page.

Removed page routes must 404 as JSON instead of rendering templates.
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


REMOVED_GET_ROUTES = [
    "/",
    "/login",
    "/logout",
    "/home",
    "/review",
    "/lessons",
    "/assignments",
    "/audit",
    "/play/1",
    "/play/attempt/1/debrief",
    "/review/asset/1",
]

REMOVED_POST_ROUTES = [
    "/login",
    "/play/1/start",
    "/assignments",
    "/review/asset/1/approve",
    "/review/asset/1/publish",
    "/attempts/1/flag",
    "/verdicts/1/override",
]


class ApiOnlyTestCase(unittest.TestCase):
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

    def test_removed_get_routes_return_json_404(self):
        for path in REMOVED_GET_ROUTES:
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 404)
                self.assertIn("error", resp.get_json())

    def test_removed_post_routes_return_json_404(self):
        for path in REMOVED_POST_ROUTES:
            with self.subTest(path=path):
                resp = self.client.post(path, json={"rationale": "x"})
                self.assertEqual(resp.status_code, 404)
                self.assertIn("error", resp.get_json())

    def test_api_health_still_served(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"ok": True})


if __name__ == "__main__":
    unittest.main()
