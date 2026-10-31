"""Content policy unit tests (pure rules, no I/O)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evolvingclass_pipeline.domain import (
    AssetKind,
    GeneratedContent,
    Tag,
)
from evolvingclass_pipeline.policy import ContentPolicy


def content(**overrides):
    args = {
        "kind": AssetKind.text,
        "title": "T",
        "body": {"text": "short"},
        "tags": (),
        "objective_refs": (),
        "rationale": "r",
    }
    args.update(overrides)
    return GeneratedContent(**args)


class PolicyCase(unittest.TestCase):
    def test_clean_content_passes(self):
        self.assertEqual(ContentPolicy().check(content()), ())

    def test_script_hooks_allowlisted(self):
        ok = content(kind=AssetKind.script,
                     body={"source": "x", "hooks": ["on_start"]})
        self.assertEqual(ContentPolicy().check(ok), ())
        bad = content(kind=AssetKind.script,
                      body={"source": "x", "hooks": ["on_start", "exec"]})
        violations = ContentPolicy().check(bad)
        self.assertEqual(len(violations), 1)
        self.assertIn("exec", violations[0])

    def test_script_hooks_must_be_list(self):
        bad = content(kind=AssetKind.script,
                      body={"source": "x", "hooks": "on_start"})
        self.assertTrue(ContentPolicy().check(bad))

    def test_text_cap(self):
        policy = ContentPolicy(max_text_chars=5)
        self.assertEqual(policy.check(content()), ())
        bad = content(body={"text": "way too long"})
        self.assertTrue(policy.check(bad))

    def test_vocabulary(self):
        policy = ContentPolicy(vocabulary={"subject": frozenset({"physics"})})
        ok = content(tags=(Tag("subject", "physics"),))
        self.assertEqual(policy.check(ok), ())
        bad = content(tags=(Tag("subject", "alchemy"),))
        self.assertTrue(policy.check(bad))
        other = content(tags=(Tag("style", "anything"),))
        self.assertEqual(policy.check(other), ())


if __name__ == "__main__":
    unittest.main()
