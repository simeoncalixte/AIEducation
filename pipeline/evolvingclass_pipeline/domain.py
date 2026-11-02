"""Pure domain value objects. Stdlib only: no I/O, no ORM, no agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class AssetKind(str, Enum):
    environment = "environment"
    prop = "prop"
    media = "media"
    text = "text"
    script = "script"
    character = "character"
    challenge = "challenge"


class DirectiveKind(str, Enum):
    brief = "brief"
    steer = "steer"


@dataclass(frozen=True)
class Tag:
    taxonomy: str
    value: str


@dataclass(frozen=True)
class DirectiveInput:
    """One active directive, as seen by generation (ids for the snapshot)."""

    id: int
    kind: DirectiveKind
    focus: str
    constraints: Mapping[str, Any]
    priority: int


@dataclass(frozen=True)
class GenerationRequest:
    kind: AssetKind
    title: str
    objectives: tuple[str, ...] = ()
    tags: tuple[Tag, ...] = ()
    directives: tuple[DirectiveInput, ...] = ()
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GeneratedContent:
    kind: AssetKind
    title: str
    body: Mapping[str, Any]
    tags: tuple[Tag, ...] = ()
    objective_refs: tuple[str, ...] = ()
    rationale: str = ""


@dataclass(frozen=True)
class LibraryMatch:
    asset_id: int
    version_id: int
    version_no: int
    score: float
    reason: str


@dataclass(frozen=True)
class DraftRef:
    asset_id: int
    version_id: int
    version_no: int


@dataclass(frozen=True)
class ProposalResult:
    reused: bool
    asset_id: int
    version_id: int
    version_no: int
    run_id: int
    preview_ref: str


@dataclass(frozen=True)
class StageAssemblyRequest:
    """Template stage assembly input (SCRUM-197)."""

    title: str
    lesson_id: int
    objectives: tuple[str, ...] = ()
    asset_version_ids: tuple[int, ...] = ()
    directives: tuple[DirectiveInput, ...] = ()
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageUse:
    """One pinned asset placement inside an assembled stage."""

    asset_version_id: int
    role: str
    position: int
    param_overrides: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageAssembly:
    """Deterministic template assembly output."""

    title: str
    lesson_id: int
    objectives: tuple[str, ...]
    uses: tuple[StageUse, ...]
    rationale: str


@dataclass(frozen=True)
class StageDraftRef:
    """Pointer to a persisted stage draft."""

    stage_id: int
    version_id: int
    version_no: int


@dataclass(frozen=True)
class StageProposalResult:
    reused: bool
    stage_id: int
    version_id: int
    version_no: int
    run_id: int


@dataclass(frozen=True)
class RunRecord:
    """Generation-run read model for run tracking (SCRUM-8 API)."""

    id: int
    agent_ref: str
    model_ref: str
    prompt_ref: str
    status: str
    attempts: int
    last_error: str | None
    params: Mapping[str, Any]
    policy_version: str


@dataclass(frozen=True)
class PreviewRequest:
    asset_id: int
    version_id: int
    version_no: int
    kind: str  # "poster" | "turntable"
    title: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    namespace: str = ""  # storage scope; "" = asset, "stage" = stage


@dataclass(frozen=True)
class PreviewResult:
    storage_ref: str


class PolicyViolation(Exception):
    """Content failed validation; carries the blocking reasons."""

    def __init__(self, violations: tuple[str, ...]) -> None:
        super().__init__("; ".join(violations))
        self.violations = violations


class GenerationFailed(Exception):
    """The backend could not produce content."""
