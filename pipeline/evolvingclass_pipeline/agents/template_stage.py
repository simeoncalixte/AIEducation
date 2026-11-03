"""Deterministic template stage assembler: offline-friendly stage drafts.

Assigns each requested asset version a position and role, producing a
pinned composition the SQLAlchemy adapter persists as a draft stage
version. A model-backed StageBackend can replace it without touching
callers.
"""

from __future__ import annotations

from typing import Mapping

from evolvingclass_pipeline.domain import (
    GenerationFailed,
    StageAssembly,
    StageAssemblyRequest,
    StageUse,
)
from evolvingclass_pipeline.ports import StageBackend

_DEFAULT_ROLES = ("backdrop", "prop", "focus")


class TemplateStageBackend(StageBackend):
    """Deterministic offline backend; swappable for model-backed ones."""

    @property
    def agent_ref(self) -> str:
        return "template-stage/v1"

    @property
    def model_ref(self) -> str:
        return "local-deterministic/v1"

    def assemble(self, request: StageAssemblyRequest) -> StageAssembly:
        title = request.title.strip()
        if not title:
            raise GenerationFailed("title is required")
        roles = self._roles(request)
        uses = tuple(
            StageUse(
                asset_version_id=version_id,
                role=roles.get(version_id, "prop"),
                position=position,
                param_overrides={},
            )
            for position, version_id in enumerate(
                request.asset_version_ids, start=1
            )
        )
        rationale = (
            f"Template assembly of {title!r} from {len(uses)} asset(s)."
        )
        if request.objectives:
            rationale += (
                "\nObjectives:\n"
                + "\n".join(f"- {o}" for o in request.objectives)
            )
        return StageAssembly(
            title=title,
            lesson_id=request.lesson_id,
            objectives=request.objectives,
            uses=uses,
            rationale=rationale,
            lesson_version_id=request.lesson_version_id,
        )

    @staticmethod
    def _roles(request: StageAssemblyRequest) -> dict[int, str]:
        declared = request.parameters.get("roles", {})
        if not isinstance(declared, Mapping):
            return {}
        roles = {}
        for position, version_id in enumerate(request.asset_version_ids):
            raw = declared.get(str(version_id), declared.get(version_id))
            if isinstance(raw, str) and raw.strip():
                roles[version_id] = raw.strip()
            else:
                roles[version_id] = _DEFAULT_ROLES[
                    position % len(_DEFAULT_ROLES)
                ]
        return roles
