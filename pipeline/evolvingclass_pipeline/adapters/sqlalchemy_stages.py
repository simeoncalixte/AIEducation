"""SQLAlchemy stage draft persistence."""

from __future__ import annotations

from collections.abc import Callable

import DataModels as db
from evolvingclass_pipeline.domain import (
    DirectiveInput,
    StageAssembly,
    StageDraftRef,
)
from evolvingclass_pipeline.ports import StageLibraryPort
from sqlalchemy import func, select
from sqlalchemy.orm import Session


class SqlAlchemyStageLibrary(StageLibraryPort):
    """Persists template assemblies as draft stage versions."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._sessions = session_factory

    def lesson_version_status(self, lesson_version_id: int) -> str | None:
        """Composition-root helper for draft checks; None when missing."""
        with self._sessions() as session:
            version = session.get(db.LessonVersion, lesson_version_id)
            return version.status.value if version is not None else None

    def manager_guide_version_id(self) -> int | None:
        """Latest published character version tagged role=manager."""
        with self._sessions() as session:
            return session.scalar(
                select(db.AssetVersion.id)
                .join(
                    db.AssetTag,
                    db.AssetTag.asset_version_id == db.AssetVersion.id,
                )
                .join(
                    db.Asset,
                    db.Asset.id == db.AssetVersion.asset_id,
                )
                .where(
                    db.Asset.kind == db.AssetKind.character,
                    db.AssetVersion.status == db.VersionStatus.published,
                    db.AssetTag.taxonomy == db.TagTaxonomy.role,
                    db.AssetTag.value == "manager",
                )
                .order_by(db.AssetVersion.id.desc())
                .limit(1)
            )

    def save_stage_draft(
        self,
        assembly: StageAssembly,
        directives: tuple[DirectiveInput, ...],
        created_by_id: int,
        run_id: int,
    ) -> StageDraftRef:
        with self._sessions() as session:
            with session.begin():
                lesson = session.get(db.Lesson, assembly.lesson_id)
                if lesson is None:
                    raise LookupError(
                        f"Unknown lesson {assembly.lesson_id}."
                    )
                for use in assembly.uses:
                    version = session.get(
                        db.AssetVersion, use.asset_version_id
                    )
                    if version is None:
                        raise LookupError(
                            f"Unknown asset version {use.asset_version_id}."
                        )
                position = (
                    session.scalar(
                        select(func.max(db.Stage.position)).where(
                            db.Stage.lesson_id == assembly.lesson_id
                        )
                    )
                    or 0
                ) + 1
                stage = db.Stage(
                    lesson_id=assembly.lesson_id, position=position,
                    title=assembly.title,
                )
                session.add(stage)
                session.flush()
                version = db.StageVersion(
                    stage_id=stage.id,
                    version_no=1,
                    status=db.VersionStatus.draft,
                    rationale=assembly.rationale,
                    generation_run_id=run_id,
                    directive_snapshot={
                        "directives": [
                            {
                                "id": d.id,
                                "kind": d.kind.value,
                                "focus": d.focus,
                                "constraints": dict(d.constraints or {}),
                                "priority": d.priority,
                            }
                            for d in directives
                        ]
                    },
                )
                session.add(version)
                session.flush()
                for use in assembly.uses:
                    session.add(db.AssetUse(
                        asset_version_id=use.asset_version_id,
                        stage_version_id=version.id,
                        position=use.position,
                        role=use.role,
                        param_overrides=dict(use.param_overrides or {}),
                    ))
                session.flush()
                position = None
                if assembly.lesson_version_id is not None:
                    lesson_version = session.get(
                        db.LessonVersion, assembly.lesson_version_id
                    )
                    if lesson_version is None:
                        raise LookupError(
                            "Unknown lesson version "
                            f"{assembly.lesson_version_id}."
                        )
                    position = (
                        session.scalar(
                            select(func.max(
                                db.LessonVersionStage.position)).where(
                                db.LessonVersionStage.lesson_version_id ==
                                assembly.lesson_version_id
                            )
                        )
                        or 0
                    ) + 1
                    session.add(db.LessonVersionStage(
                        lesson_version_id=assembly.lesson_version_id,
                        stage_version_id=version.id,
                        position=position,
                    ))
                    session.flush()
                return StageDraftRef(
                    stage_id=stage.id, version_id=version.id,
                    version_no=version.version_no,
                    composition_position=position,
                )
