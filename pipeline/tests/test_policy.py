"""Content policy unit tests (pure rules, no I/O)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evolvingclass_pipeline.domain import (
    AssetKind,
    GeneratedContent,
    GoalEvaluation,
    GoalSpec,
    Tag,
)
from evolvingclass_pipeline.policy import ContentPolicy


def goal(key="crater", rule=None, **overrides):
    args = {
        "key": key,
        "rule": {"verb": "goal-attempted", "object_ref": "crater",
                 "require": "present"},
        "evaluation": GoalEvaluation.deterministic,
        "template_ref": "label",
    }
    if rule is not None:
        args["rule"] = rule
    args.update(overrides)
    return GoalSpec(**args)


def challenge_body(**overrides):
    body = {
        "task": "Label the crater.",
        "telemetry": [{"verb": "goal-attempted", "object_ref": "crater",
                       "require": "present"}],
    }
    body.update(overrides)
    return body


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

    def test_challenge_contract_passes(self):
        ok = content(kind=AssetKind.challenge, body=challenge_body(),
                     goals=(goal(),))
        self.assertEqual(ContentPolicy().check(ok), ())

    def test_challenge_telemetry_must_be_nonempty_list(self):
        for bad_body in ({"task": "t"},
                         challenge_body(telemetry="goal-attempted"),
                         challenge_body(telemetry=[])):
            bad = content(kind=AssetKind.challenge, body=bad_body)
            self.assertTrue(ContentPolicy().check(bad), bad_body)

    def test_challenge_telemetry_entries_must_be_rules(self):
        bad = content(
            kind=AssetKind.challenge,
            body=challenge_body(telemetry=["attempted"]))
        violations = ContentPolicy().check(bad)
        self.assertTrue(violations)
        bad = content(
            kind=AssetKind.challenge,
            body=challenge_body(
                telemetry=[{"object_ref": "crater"}]))
        self.assertTrue(ContentPolicy().check(bad))

    def test_challenge_telemetry_rejects_server_verbs(self):
        bad = content(
            kind=AssetKind.challenge,
            body=challenge_body(
                telemetry=[{"verb": "goal-verdict",
                            "object_ref": "crater"}]))
        violations = ContentPolicy().check(bad)
        self.assertEqual(len(violations), 1)
        self.assertIn("goal-verdict", violations[0])

    def test_challenge_telemetry_rejects_bad_require(self):
        bad = content(
            kind=AssetKind.challenge,
            body=challenge_body(
                telemetry=[{"verb": "goal-attempted",
                            "require": "sometimes"}]))
        self.assertTrue(ContentPolicy().check(bad))
        ok = content(
            kind=AssetKind.challenge,
            body=challenge_body(
                telemetry=[{"verb": "goal-attempted",
                            "require": {"count_gte": 2}}]))
        self.assertEqual(ContentPolicy().check(ok), ())

    def test_challenge_goal_must_match_declared_telemetry(self):
        bad = content(
            kind=AssetKind.challenge, body=challenge_body(),
            goals=(goal(key="vent",
                        rule={"verb": "goal-attempted",
                              "object_ref": "vent",
                              "require": "present"}),))
        violations = ContentPolicy().check(bad)
        self.assertEqual(len(violations), 1)
        self.assertIn("vent", violations[0])

    def test_challenge_teacher_goal_requires_rubric(self):
        bad = content(
            kind=AssetKind.challenge, body=challenge_body(),
            goals=(goal(evaluation=GoalEvaluation.teacher),))
        self.assertTrue(ContentPolicy().check(bad))
        ok = content(
            kind=AssetKind.challenge, body=challenge_body(),
            goals=(goal(evaluation=GoalEvaluation.teacher,
                        rubric={"criteria": ["explains eruption"]}),))
        self.assertEqual(ContentPolicy().check(ok), ())

    def test_challenge_probe_ids_must_be_ints(self):
        ok = content(
            kind=AssetKind.challenge, body=challenge_body(),
            goals=(goal(mental_model_ids=(1,), misconception_ids=(2,)),))
        self.assertEqual(ContentPolicy().check(ok), ())
        bad = content(
            kind=AssetKind.challenge, body=challenge_body(),
            goals=(goal(mental_model_ids=("1",)),))
        self.assertTrue(ContentPolicy().check(bad))

    def test_challenge_goal_keys_must_be_unique(self):
        bad = content(
            kind=AssetKind.challenge, body=challenge_body(),
            goals=(goal(key="dup"), goal(key="dup")))
        violations = ContentPolicy().check(bad)
        self.assertEqual(len(violations), 1)
        self.assertIn("dup", violations[0])

    def test_character_dialogue_bounds_pass(self):
        ok = content(
            kind=AssetKind.character,
            body={"name": "Manager", "role": "guide",
                  "dialogue": [{"speaker": "guide",
                                "line": "Welcome."}]})
        self.assertEqual(ContentPolicy().check(ok), ())

    def test_character_dialogue_must_be_bounded_entries(self):
        bad = content(kind=AssetKind.character,
                      body={"name": "M", "dialogue": "Welcome."})
        self.assertTrue(ContentPolicy().check(bad))
        bad = content(
            kind=AssetKind.character,
            body={"name": "M", "dialogue": ["Welcome."]})
        self.assertTrue(ContentPolicy().check(bad))
        bad = content(
            kind=AssetKind.character,
            body={"name": "M",
                  "dialogue": [{"speaker": "guide", "line": ""}]})
        self.assertTrue(ContentPolicy().check(bad))

    def test_character_dialogue_caps(self):
        policy = ContentPolicy(max_dialogue_lines=1,
                               max_dialogue_line_chars=5)
        bad = content(
            kind=AssetKind.character,
            body={"name": "M",
                  "dialogue": [{"speaker": "g", "line": "ok"},
                               {"speaker": "g", "line": "ok"}]})
        self.assertTrue(policy.check(bad))
        bad = content(
            kind=AssetKind.character,
            body={"name": "M",
                  "dialogue": [{"speaker": "g", "line": "too long"}]})
        self.assertTrue(policy.check(bad))


if __name__ == "__main__":
    unittest.main()
