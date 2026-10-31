"""SVG preview determinism and versioned paths."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evolvingclass_pipeline.adapters.svg_preview import SvgPreviewRenderer
from evolvingclass_pipeline.domain import PreviewRequest


def request(**overrides):
    args = {"asset_id": 4, "version_id": 8, "version_no": 2,
            "kind": "poster", "title": "Gravity",
            "metadata": {"asset_kind": "text", "objectives": ["falling"]}}
    args.update(overrides)
    return PreviewRequest(**args)


class SvgPreviewCase(unittest.TestCase):
    def test_poster_deterministic_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = SvgPreviewRenderer(tmp).render(request()).storage_ref
            second = SvgPreviewRenderer(tmp).render(request()).storage_ref
            self.assertEqual(first, second)
            self.assertEqual(first, "4/v2_poster.svg")
            with open(os.path.join(tmp, first), "rb") as fh:
                before = fh.read()
            SvgPreviewRenderer(tmp).render(request())
            with open(os.path.join(tmp, first), "rb") as fh:
                self.assertEqual(fh.read(), before)

    def test_turntable_differs_and_versions_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            renderer = SvgPreviewRenderer(tmp)
            poster = renderer.render(request()).storage_ref
            strip = renderer.render(request(kind="turntable")).storage_ref
            self.assertEqual(strip, "4/v2_turntable.svg")
            with open(os.path.join(tmp, poster), "rb") as fh:
                poster_bytes = fh.read()
            with open(os.path.join(tmp, strip), "rb") as fh:
                self.assertNotEqual(fh.read(), poster_bytes)

    def test_namespace_scopes_stage_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = SvgPreviewRenderer(tmp).render(
                request(namespace="stage")).storage_ref
            self.assertEqual(ref, "stage/4/v2_poster.svg")
            self.assertTrue(os.path.exists(os.path.join(tmp, ref)))


if __name__ == "__main__":
    unittest.main()
