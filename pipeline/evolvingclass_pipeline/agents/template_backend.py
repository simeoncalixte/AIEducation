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
)
from evolvingclass_pipeline.ports import GenerationBackend


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
        )

    @staticmethod
    def _body_for(
        kind: AssetKind, title: str, parameters: Mapping[str, Any]
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
                "dialogue": [f"Welcome to {title}."],
                "parameters": params,
            }
        if kind is AssetKind.challenge:
            return {
                "task": f"Complete {title}.",
                "telemetry": ["attempted", "completed", "scored"],
                "parameters": params,
            }
        return {"description": f"Template {kind.value}: {title}.", "parameters": params}
