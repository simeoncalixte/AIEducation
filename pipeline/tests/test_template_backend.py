"""Template backend: determinism, provenance, failure surface."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evolvingclass_pipeline.agents.template_backend import TemplateAssetBackend
from evolvingclass_pipeline.domain import (
    AssetKind,
    GenerationFailed,
    GenerationRequest,
)
from evolvingclass_pipeline.policy import ContentPolicy
from evolvingclass_pipeline.ports import GenerationBackend


class TemplateCase(unittest.TestCase):
    def setUp(self):
        self.backend = TemplateAssetBackend()

    def test_is_a_port(self):
        self.assertIsInstance(self.backend, GenerationBackend)

    def test_provenance_refs(self):
        self.assertTrue(self.backend.agent_ref)
        self.assertTrue(self.backend.model_ref)

    def test_deterministic(self):
        req = GenerationRequest(kind=AssetKind.text, title="Gravity",
                                objectives=("falling",))
        first = self.backend.generate(req)
        second = self.backend.generate(req)
        self.assertEqual(first, second)

    def test_empty_title_fails(self):
        with self.assertRaises(GenerationFailed):
            self.backend.generate(
                GenerationRequest(kind=AssetKind.text, title="  "))

    def test_script_output_passes_default_policy(self):
        content = self.backend.generate(
            GenerationRequest(kind=AssetKind.script, title="Intro"))
        self.assertEqual(ContentPolicy().check(content), ())


if __name__ == "__main__":
    unittest.main()
