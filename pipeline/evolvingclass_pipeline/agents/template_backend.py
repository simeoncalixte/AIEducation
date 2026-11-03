"""Deterministic template backend: offline-friendly generation for the pilot.

Builds well-formed asset content from the brief without model calls, so the
pipeline, policy, and adapters stay testable with zero credentials. A
model-backed GenerationBackend can replace it without touching callers.
"""

from __future__ import annotations

from typing import Any, Mapping

from evolvingclass_pipeline.domain import (
    AssetKind,
    GeneratedContent,
    GenerationFailed,
    GenerationRequest,
    GoalEvaluation,
    GoalSpec,
)
from evolvingclass_pipeline.ports import GenerationBackend

_CHALLENGE_TEMPLATE_REF = "template-challenge/v1"
_TEACHER_TEMPLATE_REF = "template-teacher/v1"


def _slug(title: str) -> str:
    words = "".join(
        ch.lower() if ch.isalnum() else " " for ch in title
    ).split()
    return "-".join(words) or "challenge"


def _id_list(parameters: Mapping[str, Any], field: str) -> tuple[int, ...]:
    value = parameters.get(field, ())
    if not isinstance(value, (tuple, list)) or any(
        not isinstance(i, int) or isinstance(i, bool) for i in value
    ):
        raise GenerationFailed(f"'{field}' must hold integers.")
    return tuple(value)


def _teacher_specs(
    parameters: Mapping[str, Any], taken: set[str]
) -> list[GoalSpec]:
    entries = parameters.get("teacher_goals", ())
    if not isinstance(entries, (tuple, list)):
        raise GenerationFailed("'teacher_goals' must be a list.")
    specs = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise GenerationFailed(
                "Each teacher goal needs a key and a rubric.")
        key = entry.get("key")
        rubric = entry.get("rubric")
        if (
            not isinstance(key, str)
            or not key
            or not isinstance(rubric, dict)
        ):
            raise GenerationFailed(
                "Each teacher goal needs a string key and a "
                "rubric object.")
        if key in taken:
            raise GenerationFailed(
                f"Duplicate teacher goal key {key!r}.")
        taken.add(key)
        template_ref = entry.get("template_ref", _TEACHER_TEMPLATE_REF)
        if not isinstance(template_ref, str) or not template_ref:
            raise GenerationFailed(
                "Teacher goal template_ref must be a string.")
        model_ids = (
            _id_list(entry, "mental_model_ids")
            if "mental_model_ids" in entry
            else ()
        )
        misc_ids = (
            _id_list(entry, "misconception_ids")
            if "misconception_ids" in entry
            else ()
        )
        specs.append(
            GoalSpec(
                key=key,
                rule={},
                evaluation=GoalEvaluation.teacher,
                rubric=dict(rubric),
                template_ref=template_ref,
                mental_model_ids=model_ids,
                misconception_ids=misc_ids,
            )
        )
    return specs


class TemplateAssetBackend(GenerationBackend):
    """Deterministic offline backend; swappable for model-backed ones (LSP)."""

    @property
    def agent_ref(self) -> str:
        return "template-backend/v1"

    @property
    def model_ref(self) -> str:
        return "local-deterministic/v1"

    def generate(self, request: GenerationRequest) -> GeneratedContent:
        title = request.title.strip()
        if not title:
            raise GenerationFailed("title is required")
        body = self._body_for(request.kind, title, request.parameters)
        objectives = "\n".join(f"- {o}" for o in request.objectives)
        rationale = (
            f"Template draft for {title!r} ({request.kind.value}) "
            f"from {len(request.directives)} directive(s)."
            + (f"\nObjectives:\n{objectives}" if objectives else "")
        )
        return GeneratedContent(
            kind=request.kind,
            title=title,
            body=body,
            tags=request.tags,
            objective_refs=request.objectives,
            rationale=rationale,
            goals=self._goals_for(
                request.kind, title, request.parameters),
        )

    @classmethod
    def _body_for(
        cls, kind: AssetKind, title: str, parameters: Mapping[str, Any]
    ) -> dict[str, Any]:
        params = dict(parameters)
        if kind is AssetKind.text:
            return {"text": f"# {title}\n\n[template body]\n", "parameters": params}
        if kind is AssetKind.script:
            return {
                "source": f"# {title}\n# template behavior\n",
                "hooks": ["on_start", "on_complete"],
                "parameters": params,
            }
        if kind is AssetKind.character:
            return {
                "name": title,
                "role": "guide",
                "dialogue": [
                    {"speaker": "guide",
                     "line": f"Welcome to {title}."}
                ],
                "parameters": params,
            }
        if kind is AssetKind.challenge:
            return {
                "task": f"Complete {title}.",
                "telemetry": [cls._contract_for(title)],
                "parameters": params,
            }
        return {"description": f"Template {kind.value}: {title}.", "parameters": params}

    @staticmethod
    def _contract_for(title: str) -> dict[str, Any]:
        return {
            "verb": "goal-attempted",
            "object_ref": _slug(title),
            "require": "present",
        }

    @classmethod
    def _goals_for(
        cls, kind: AssetKind, title: str, parameters: Mapping[str, Any]
    ) -> tuple[GoalSpec, ...]:
        if kind is not AssetKind.challenge:
            return ()
        rule = cls._contract_for(title)
        specs = [
            GoalSpec(
                key=rule["object_ref"],
                rule=dict(rule),
                evaluation=GoalEvaluation.deterministic,
                template_ref=_CHALLENGE_TEMPLATE_REF,
                mental_model_ids=_id_list(
                    parameters, "mental_model_ids"),
                misconception_ids=_id_list(
                    parameters, "misconception_ids"),
            )
        ]
        specs.extend(
            _teacher_specs(parameters, {specs[0].key}))
        return tuple(specs)
