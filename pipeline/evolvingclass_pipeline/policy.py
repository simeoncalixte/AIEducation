"""Pure content-validation rules. No I/O: trivially testable, safely shared."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from evolvingclass_pipeline.domain import (
    AssetKind,
    GeneratedContent,
    GoalEvaluation,
)

# Body field carrying human/AI-readable text per kind, for length caps.
_TEXT_FIELDS: dict[AssetKind, str] = {
    AssetKind.text: "text",
    AssetKind.script: "source",
}


@dataclass(frozen=True)
class ContentPolicy:
    """Pilot content policy.

    - Script bodies may only use allowlisted hooks.
    - Challenge bodies must declare a telemetry contract: a
      non-empty list of rule-shaped events using client verbs, and
      every deterministic goal must match a declared event.
    - Character dialogue must be bounded speaker/line entries.
    - Text-bearing bodies respect a length cap.
    - Controlled taxonomies must use vocabulary values (empty vocab
      disables that check).
    """

    allowed_script_hooks: frozenset[str] = frozenset(
        {"on_start", "on_complete", "on_timeout", "on_hint"}
    )
    reserved_server_verbs: frozenset[str] = frozenset({"goal-verdict"})
    max_text_chars: int = 20_000
    max_dialogue_lines: int = 50
    max_dialogue_line_chars: int = 2000
    vocabulary: Mapping[str, frozenset[str]] = field(default_factory=dict)

    def check(self, content: GeneratedContent) -> tuple[str, ...]:
        violations: list[str] = []
        if content.kind is AssetKind.script:
            hooks = content.body.get("hooks", [])
            if not isinstance(hooks, list):
                violations.append("script body must carry a hooks list")
            else:
                unknown = [h for h in hooks if h not in self.allowed_script_hooks]
                if unknown:
                    violations.append(
                        f"script hooks outside allowlist: {sorted(unknown)}"
                    )
        if content.kind is AssetKind.challenge:
            violations.extend(self._check_telemetry(content))
        if content.kind is AssetKind.character:
            violations.extend(self._check_dialogue(content))
        text_field = _TEXT_FIELDS.get(content.kind)
        if text_field is not None:
            text = content.body.get(text_field, "")
            if isinstance(text, str) and len(text) > self.max_text_chars:
                violations.append(
                    f"{text_field} exceeds {self.max_text_chars} chars"
                )
        for taxonomy, allowed in self.vocabulary.items():
            for tag in content.tags:
                if tag.taxonomy == taxonomy and tag.value not in allowed:
                    violations.append(
                        f"tag {taxonomy}:{tag.value} outside vocabulary"
                    )
        return tuple(violations)

    def _check_telemetry(self, content: GeneratedContent) -> list[str]:
        violations: list[str] = []
        telemetry = content.body.get("telemetry")
        if not isinstance(telemetry, list):
            return ["challenge body must carry a telemetry list"]
        if not telemetry:
            return ["challenge telemetry must declare at least one event"]
        declared: set[tuple[str, str | None]] = set()
        for index, entry in enumerate(telemetry):
            where = f"telemetry[{index}]"
            if not isinstance(entry, dict):
                violations.append(f"{where} must be a rule-shaped object")
                continue
            violations.extend(self._check_rule(entry, where))
            verb = entry.get("verb")
            ref = entry.get("object_ref")
            if isinstance(verb, str) and verb:
                declared.add(
                    (verb, ref if isinstance(ref, str) else None))
        seen_keys: set[str] = set()
        for spec in content.goals:
            if spec.key in seen_keys:
                violations.append(
                    f"duplicate goal key {spec.key!r}"
                )
            seen_keys.add(spec.key)
            for label, ids in (("mental_model_ids",
                                spec.mental_model_ids),
                               ("misconception_ids",
                                spec.misconception_ids)):
                if not isinstance(ids, (tuple, list)) or any(
                    not isinstance(i, int) or isinstance(i, bool)
                    for i in ids
                ):
                    violations.append(
                        f"goal {spec.key!r} {label} must hold integers"
                    )
            if spec.evaluation is not GoalEvaluation.deterministic:
                if spec.rubric is None:
                    violations.append(
                        f"goal {spec.key!r} needs a rubric for "
                        "teacher evaluation"
                    )
                continue
            where = f"goal {spec.key!r}"
            if not isinstance(spec.rule, dict):
                violations.append(f"{where} rule must be an object")
                continue
            violations.extend(self._check_rule(spec.rule, where))
            want_ref = spec.rule.get("object_ref")
            if not any(
                verb == spec.rule.get("verb")
                and (want_ref is None or ref == want_ref)
                for verb, ref in declared
            ):
                violations.append(
                    f"{where} matches no declared telemetry event"
                )
        return violations

    def _check_rule(self, rule: dict[str, Any], where: str) -> list[str]:
        """Mirror the goals/v1 evaluator's rule shape (service/goals)."""
        violations: list[str] = []
        verb = rule.get("verb")
        if not isinstance(verb, str) or not verb:
            violations.append(f"{where} needs a string verb")
        elif verb in self.reserved_server_verbs:
            violations.append(
                f"{where} uses server-only verb {verb!r}"
            )
        ref = rule.get("object_ref")
        if ref is not None and not isinstance(ref, str):
            violations.append(f"{where} object_ref must be a string")
        require = rule.get("require", "present")
        if require in ("present", "absent"):
            return violations
        if (
            isinstance(require, dict)
            and isinstance(require.get("count_gte"), int)
            and not isinstance(require.get("count_gte"), bool)
        ):
            return violations
        violations.append(
            f"{where} require must be present, absent, or "
            "{count_gte: int}"
        )
        return violations

    def _check_dialogue(self, content: GeneratedContent) -> list[str]:
        violations: list[str] = []
        dialogue = content.body.get("dialogue")
        if not isinstance(dialogue, list):
            return ["character body must carry a dialogue list"]
        if len(dialogue) > self.max_dialogue_lines:
            violations.append(
                f"dialogue exceeds {self.max_dialogue_lines} lines"
            )
        for index, entry in enumerate(dialogue):
            where = f"dialogue[{index}]"
            if not isinstance(entry, dict):
                violations.append(
                    f"{where} must hold speaker and line"
                )
                continue
            speaker = entry.get("speaker")
            line = entry.get("line")
            if not isinstance(speaker, str) or not speaker:
                violations.append(f"{where} needs a string speaker")
            if not isinstance(line, str) or not line:
                violations.append(f"{where} needs a string line")
            elif len(line) > self.max_dialogue_line_chars:
                violations.append(
                    f"{where} exceeds "
                    f"{self.max_dialogue_line_chars} chars"
                )
        return violations
