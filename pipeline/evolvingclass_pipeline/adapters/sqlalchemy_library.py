"""SQLAlchemy adapters for the library and run-store ports.

Owns all ORM mapping between pipeline domain objects and DataModels rows,
including enum translation by value.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

import DataModels as db
from evolvingclass_pipeline.domain import (
    AssetKind,
    DraftRef,
    GeneratedContent,
    LibraryMatch,
    RunRecord,
    Tag,
)
from evolvingclass_pipeline.ports import AssetLibraryPort, RunStore
from sqlalchemy.orm import Session


def _db_kind(kind: AssetKind) -> db.AssetKind:
    return db.AssetKind(kind.value)


class SqlAlchemyAssetLibrary(AssetLibraryPort):
    """Published-only candidate search plus draft persistence."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._sessions = session_factory

    def actor_exists(self, user_id: int) -> bool:
        """Composition-root helper so the API can 404 unknown authors."""
        with self._sessions() as session:
            return session.get(db.AppUser, user_id) is not None

    def find_candidates(
        self,
        kind: AssetKind,
        tags: Sequence[Tag],
        objectives: Sequence[str],
        limit: int = 5,
    ) -> list[LibraryMatch]:
        wanted = {f"{t.taxonomy}:{t.value}" for t in tags} | set(objectives)
        with self._sessions() as session:
            rows = (
                session.query(db.AssetVersion, db.Asset)
                .join(db.Asset, db.AssetVersion.asset_id == db.Asset.id)
                .filter(
                    db.Asset.kind == _db_kind(kind),
                    db.AssetVersion.status == db.VersionStatus.published,
                )
                .order_by(db.AssetVersion.id.desc())
                .all()
            )
            scored: list[LibraryMatch] = []
            for version, asset in rows:
                terms = {f"{t.taxonomy.value}:{t.value}" for t in version.tags}
                terms |= set(version.objective_refs or [])
                matched = wanted & terms if wanted else set()
                union = wanted | terms
                score = len(matched) / len(union) if union else 0.0
                reason = (
                    f"matched {sorted(matched)}" if matched else "no shared terms"
                )
                scored.append(
                    LibraryMatch(
                        asset_id=asset.id,
                        version_id=version.id,
                        version_no=version.version_no,
                        score=score,
                        reason=reason,
                    )
                )
        scored.sort(key=lambda m: (-m.score, -m.version_id))
        return scored[:limit]

    def save_draft(
        self,
        content: GeneratedContent,
        content_ref: str,
        snapshot: Mapping[str, Any],
        run_id: int,
        created_by_id: int,
        asset_id: int | None = None,
    ) -> DraftRef:
        with self._sessions() as session:
            with session.begin():
                if asset_id is None:
                    asset = db.Asset(
                        kind=_db_kind(content.kind),
                        title=content.title,
                        created_by_id=created_by_id,
                    )
                    session.add(asset)
                    session.flush()
                    version_no = 1
                else:
                    asset = session.get(db.Asset, asset_id)
                    if asset is None:
                        raise LookupError(f"asset {asset_id} not found")
                    latest = (
                        session.query(db.AssetVersion.version_no)
                        .filter_by(asset_id=asset_id)
                        .order_by(db.AssetVersion.version_no.desc())
                        .first()
                    )
                    version_no = (latest[0] if latest else 0) + 1
                version = db.AssetVersion(
                    asset_id=asset.id,
                    version_no=version_no,
                    status=db.VersionStatus.draft,
                    rationale=content.rationale,
                    objective_refs=list(content.objective_refs),
                    content_ref=content_ref,
                    param_schema={},
                    generation_run_id=run_id,
                    directive_snapshot=dict(snapshot),
                )
                session.add(version)
                session.flush()
                for tag in content.tags:
                    session.add(
                        db.AssetTag(
                            asset_version_id=version.id,
                            taxonomy=db.TagTaxonomy(tag.taxonomy),
                            value=tag.value,
                        )
                    )
                return DraftRef(
                    asset_id=asset.id, version_id=version.id, version_no=version_no
                )

    def record_preview(
        self, version_id: int, kind: str, storage_ref: str
    ) -> None:
        with self._sessions() as session:
            with session.begin():
                session.add(
                    db.PreviewArtifact(
                        asset_version_id=version_id,
                        kind=db.PreviewKind(kind),
                        storage_ref=storage_ref,
                    )
                )


class SqlAlchemyRunStore(RunStore):
    """Run lifecycle rows; failed attempts accumulate for retry triage."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._sessions = session_factory

    def begin_run(
        self,
        agent_ref: str,
        model_ref: str,
        prompt_ref: str,
        params: Mapping[str, Any],
        policy_version: str,
    ) -> int:
        with self._sessions() as session:
            with session.begin():
                run = db.GenerationRun(
                    agent_ref=agent_ref,
                    model_ref=model_ref,
                    prompt_ref=prompt_ref,
                    params=dict(params),
                    status=db.GenerationStatus.queued,
                    policy_version=policy_version,
                )
                session.add(run)
                session.flush()
                return run.id

    def mark_running(self, run_id: int) -> None:
        self._set_status(run_id, db.GenerationStatus.running)

    def mark_completed(self, run_id: int) -> None:
        self._set_status(run_id, db.GenerationStatus.completed)

    def mark_failed(self, run_id: int, error: str) -> None:
        with self._sessions() as session:
            with session.begin():
                run = session.get(db.GenerationRun, run_id)
                if run is None:
                    raise LookupError(f"run {run_id} not found")
                run.status = db.GenerationStatus.failed
                run.attempts = (run.attempts or 0) + 1
                run.last_error = error[:2000]

    def _set_status(self, run_id: int, status: db.GenerationStatus) -> None:
        with self._sessions() as session:
            with session.begin():
                run = session.get(db.GenerationRun, run_id)
                if run is None:
                    raise LookupError(f"run {run_id} not found")
                run.status = status

    def list_runs(
        self, status: str | None = None, limit: int = 50
    ) -> list[RunRecord]:
        with self._sessions() as session:
            query = session.query(db.GenerationRun)
            if status is not None:
                query = query.filter(
                    db.GenerationRun.status == db.GenerationStatus(status)
                )
            rows = (
                query.order_by(db.GenerationRun.id.desc())
                .limit(max(1, limit))
                .all()
            )
            return [self._record(row) for row in rows]

    def get_run(self, run_id: int) -> RunRecord:
        with self._sessions() as session:
            row = session.get(db.GenerationRun, run_id)
            if row is None:
                raise LookupError(f"run {run_id} not found")
            return self._record(row)

    @staticmethod
    def _record(row: db.GenerationRun) -> RunRecord:
        return RunRecord(
            id=row.id,
            agent_ref=row.agent_ref,
            model_ref=row.model_ref,
            prompt_ref=row.prompt_ref,
            status=row.status.value,
            attempts=row.attempts or 0,
            last_error=row.last_error,
            params=dict(row.params or {}),
            policy_version=row.policy_version or "",
        )
