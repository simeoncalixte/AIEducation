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
    GoalEvaluation,
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

    def test_challenge_output_ships_contract_and_goals(self):
        content = self.backend.generate(
            GenerationRequest(kind=AssetKind.challenge,
                              title="Label the Crater"))
        self.assertEqual(ContentPolicy().check(content), ())
        telemetry = content.body["telemetry"]
        self.assertTrue(telemetry)
        self.assertTrue(
            all(isinstance(e, dict) and e.get("verb") for e in telemetry))
        self.assertEqual(len(content.goals), 1)
        spec = content.goals[0]
        self.assertEqual(spec.rule["verb"], telemetry[0]["verb"])
        self.assertEqual(spec.rule.get("object_ref"),
                         telemetry[0].get("object_ref"))
        self.assertTrue(spec.template_ref)

    def test_character_output_has_bounded_dialogue(self):
        content = self.backend.generate(
            GenerationRequest(kind=AssetKind.character,
                              title="Manager"))
        self.assertEqual(ContentPolicy().check(content), ())
        dialogue = content.body["dialogue"]
        self.assertTrue(dialogue)
        for entry in dialogue:
            self.assertTrue(entry["speaker"])
            self.assertTrue(entry["line"])

    def test_challenge_probe_parameters_land_on_goals(self):
        content = self.backend.generate(
            GenerationRequest(kind=AssetKind.challenge,
                              title="Label the Crater",
                              parameters={"mental_model_ids": [3],
                                          "misconception_ids": [7, 8]}))
        self.assertEqual(ContentPolicy().check(content), ())
        self.assertEqual(content.goals[0].mental_model_ids, (3,))
        self.assertEqual(content.goals[0].misconception_ids, (7, 8))

    def test_challenge_teacher_goals_need_rubrics(self):
        content = self.backend.generate(
            GenerationRequest(
                kind=AssetKind.challenge, title="Explain Eruptions",
                parameters={"teacher_goals": [
                    {"key": "explain",
                     "rubric": {"criteria": ["names magma"]}}]}))
        self.assertEqual(ContentPolicy().check(content), ())
        teacher = [g for g in content.goals
                   if g.evaluation is GoalEvaluation.teacher]
        self.assertEqual(len(teacher), 1)
        self.assertEqual(teacher[0].rubric,
                         {"criteria": ["names magma"]})

    def test_challenge_bad_probe_parameters_fail(self):
        with self.assertRaises(GenerationFailed):
            self.backend.generate(
                GenerationRequest(kind=AssetKind.challenge,
                                  title="T",
                                  parameters={"mental_model_ids": ["x"]}))
        with self.assertRaises(GenerationFailed):
            self.backend.generate(
                GenerationRequest(
                    kind=AssetKind.challenge, title="T",
                    parameters={"teacher_goals": [{"key": "k"}]}))
        with self.assertRaises(GenerationFailed):
            self.backend.generate(
                GenerationRequest(
                    kind=AssetKind.challenge, title="T",
                    parameters={"teacher_goals": [
                        {"key": "a", "rubric": {"c": []}},
                        {"key": "a", "rubric": {"c": []}}]}))


if __name__ == "__main__":
    unittest.main()
