"""Abstract boundaries. The pipeline depends on these, never on backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping, Sequence

from evolvingclass_pipeline.domain import (
    AssetKind,
    DraftRef,
    GeneratedContent,
    GenerationRequest,
    LibraryMatch,
    PreviewRequest,
    PreviewResult,
    Tag,
)


class GenerationBackend(ABC):
    """Produces asset content. Template today, model-backed tomorrow."""

    @property
    @abstractmethod
    def agent_ref(self) -> str: ...

    @property
    @abstractmethod
    def model_ref(self) -> str: ...

    @abstractmethod
    def generate(self, request: GenerationRequest) -> GeneratedContent: ...


class AssetLibraryPort(ABC):
    """Library search and draft persistence, without storage details."""

    @abstractmethod
    def find_candidates(
        self,
        kind: AssetKind,
        tags: Sequence[Tag],
        objectives: Sequence[str],
        limit: int = 5,
    ) -> list[LibraryMatch]: ...

    @abstractmethod
    def save_draft(
        self,
        content: GeneratedContent,
        content_ref: str,
        snapshot: Mapping[str, Any],
        run_id: int,
        created_by_id: int,
        asset_id: int | None = None,
    ) -> DraftRef: ...

    @abstractmethod
    def record_preview(
        self,
        version_id: int,
        kind: str,
        storage_ref: str,
    ) -> None:
        """Pin a rendered preview artifact to an asset version."""


class RunStore(ABC):
    """Generation-run lifecycle, independent of the library."""

    @abstractmethod
    def begin_run(
        self,
        agent_ref: str,
        model_ref: str,
        prompt_ref: str,
        params: Mapping[str, Any],
        policy_version: str,
    ) -> int: ...

    @abstractmethod
    def mark_running(self, run_id: int) -> None: ...

    @abstractmethod
    def mark_completed(self, run_id: int) -> None: ...

    @abstractmethod
    def mark_failed(self, run_id: int, error: str) -> None: ...


class ContentStore(ABC):
    """Blob storage for version bodies, keyed by content hash."""

    @abstractmethod
    def put(self, body: Mapping[str, Any]) -> str: ...

    @abstractmethod
    def get(self, storage_ref: str) -> Mapping[str, Any]: ...


class PreviewPort(ABC):
    """Poster/turntable rendering for draft and published versions."""

    @abstractmethod
    def render(self, request: PreviewRequest) -> PreviewResult: ...
