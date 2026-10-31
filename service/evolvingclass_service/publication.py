"""Publication transaction: publish / rollback / retire version graphs.

Guarantees (one database transaction per call):
  1. The actor is authorized (teacher/admin with an active membership in
     the owning classroom or school; global assets require admin).
  2. The version is in the expected starting status.
  3. The latest approval decision on the version is ``approved``.
  4. Every dependency in the version graph is already published
     (lesson composition, stage asset uses, challenge goals).
  5. The status flip and the ``publish_event`` audit row commit together.

Immutability of published content is a service rule enforced through
:func:`ensure_draft`: every mutating writer must call it before touching
a version or its linked rows (composition, asset uses, goals, tags).
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from DataModels import (
    AppUser,
    Approval,
    AssetKind,
    Classroom,
    AssetVersion,
    Decision,
    LessonVersion,
    Membership,
    MembershipStatus,
    PreviewArtifact,
    PreviewKind,
    PublishAction,
    PublishEvent,
    StageVersion,
    UserRole,
    VersionStatus,
)

from .errors import (
    EMPTY_COMPOSITION,
    FORBIDDEN,
    MISSING_GOALS,
    NOT_APPROVED,
    NOT_DRAFT,
    NOT_FOUND,
    NOT_PUBLISHED,
    NOT_RETIRED,
    NOTHING_LIVE,
    UNPUBLISHED_DEPENDENCY,
    PublicationError,
)

SessionFactory = Callable[[], Session]

# Renders a publish-time preview: (kind, version_id) ->
# (preview_kind, storage_ref), or None to skip. Lessons have no
# preview slot in the model, so the service never calls it for them.
PreviewFinalizer = Callable[[str, int], tuple[str, str] | None]

_PUBLISHERS = frozenset({UserRole.teacher, UserRole.admin})


@dataclass(frozen=True)
class PublishResult:
    """Outcome of a successful publication transaction."""

    version_kind: str  # "asset" | "stage" | "lesson"
    version_id: int
    version_no: int
    status: str
    event_ids: tuple[int, ...]


# ---------------------------------------------------------------------------
# Freeze guard
# ---------------------------------------------------------------------------


def ensure_draft(version: AssetVersion | StageVersion | LessonVersion) -> None:
    """Reject writes to anything that is not a draft.

    Call this at the top of every mutating path that touches a version
    graph (composition, asset uses, goals, tags, requirements).
    """
    if version.status is not VersionStatus.draft:
        raise PublicationError(
            NOT_DRAFT,
            f"Version {version.id} is {version.status.value}; only drafts are mutable.",
        )


# ---------------------------------------------------------------------------
# Internal checks (each takes an open Session; callers own the transaction)
# ---------------------------------------------------------------------------


def _get(session: Session, model: type, version_id: int, kind: str):
    version = session.get(model, version_id)
    if version is None:
        raise PublicationError(NOT_FOUND, f"Unknown {kind} version {version_id}.")
    return version


def _require_status(version, expected: VersionStatus, code: str, verb: str) -> None:
    if version.status is not expected:
        raise PublicationError(
            code,
            f"Cannot {verb} version {version.id}: status is "
            f"{version.status.value}, expected {expected.value}.",
        )


def _check_actor(
    session: Session, actor_id: int, school_id: int | None, classroom_id: int | None
) -> None:
    """Pilot authorization: publisher role + active local membership."""
    actor = session.get(AppUser, actor_id)
    if actor is None:
        raise PublicationError(NOT_FOUND, f"Unknown actor {actor_id}.")
    if actor.role not in _PUBLISHERS:
        raise PublicationError(
            FORBIDDEN,
            f"Role {actor.role.value} may not publish; teacher or admin required.",
        )
    if school_id is None:
        # Global asset: admin role required, any active membership suffices.
        if actor.role is not UserRole.admin:
            raise PublicationError(
                FORBIDDEN, "Global assets may only be published by an admin."
            )
        has_any = session.scalar(
            select(Membership.id).where(
                Membership.user_id == actor_id,
                Membership.status == MembershipStatus.active,
            )
        )
        if has_any is None:
            raise PublicationError(FORBIDDEN, "Actor has no active membership.")
        return
    # School scope covers classroom memberships inside that school.
    scope = (Membership.school_id == school_id) | (
        Classroom.school_id == school_id
    )
    if classroom_id is not None:
        scope = scope | (Membership.classroom_id == classroom_id)
    local = session.scalar(
        select(Membership.id)
        .outerjoin(Classroom, Membership.classroom_id == Classroom.id)
        .where(
            Membership.user_id == actor_id,
            Membership.status == MembershipStatus.active,
            scope,
        )
    )
    if local is None:
        raise PublicationError(
            FORBIDDEN, "Actor has no active membership in this school/classroom."
        )


def _check_approved(session: Session, version, kind: str) -> None:
    """The latest approval decision must be ``approved``."""
    column = {
        "asset": Approval.asset_version_id,
        "stage": Approval.stage_version_id,
        "lesson": Approval.lesson_version_id,
    }[kind]
    latest = session.scalar(
        select(Approval)
        .where(column == version.id)
        .order_by(desc(Approval.decided_at), desc(Approval.id))
        .limit(1)
    )
    if latest is None or latest.decision is not Decision.approved:
        raise PublicationError(
            NOT_APPROVED, f"Version {version.id} has no current approval."
        )


def _check_asset_publishable(session: Session, version: AssetVersion) -> None:
    if version.asset.kind is AssetKind.challenge and not version.goals:
        raise PublicationError(
            MISSING_GOALS,
            f"Challenge version {version.id} defines no goals.",
        )


def _check_stage_publishable(session: Session, version: StageVersion) -> None:
    for use in version.asset_uses:
        if use.asset_version.status is not VersionStatus.published:
            raise PublicationError(
                UNPUBLISHED_DEPENDENCY,
                f"Stage version {version.id} uses asset version "
                f"{use.asset_version_id} ({use.asset_version.status.value}).",
            )


def _check_lesson_publishable(session: Session, version: LessonVersion) -> None:
    if not version.composition:
        raise PublicationError(
            EMPTY_COMPOSITION,
            f"Lesson version {version.id} pins no stage versions.",
        )
    for link in version.composition:
        if link.stage_version.status is not VersionStatus.published:
            raise PublicationError(
                UNPUBLISHED_DEPENDENCY,
                f"Lesson version {version.id} pins stage version "
                f"{link.stage_version_id} ({link.stage_version.status.value}).",
            )


def _record_event(
    session: Session,
    version,
    kind: str,
    action: PublishAction,
    actor_id: int,
    rationale: str,
) -> PublishEvent:
    event = PublishEvent(
        asset_version_id=version.id if kind == "asset" else None,
        stage_version_id=version.id if kind == "stage" else None,
        lesson_version_id=version.id if kind == "lesson" else None,
        action=action,
        actor_id=actor_id,
        rationale=rationale,
    )
    session.add(event)
    session.flush()
    return event


def _stamp_live(version: LessonVersion) -> None:
    version.published_at = _dt.datetime.now(_dt.timezone.utc)


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------


def _finalize_preview(
    session: Session,
    kind: str,
    version,
    finalize_preview: PreviewFinalizer,
) -> None:
    """Pin the publish-time preview artifact, unless one already exists."""
    column = {
        "asset": PreviewArtifact.asset_version_id,
        "stage": PreviewArtifact.stage_version_id,
    }[kind]
    existing = session.scalar(
        select(PreviewArtifact.id).where(column == version.id).limit(1)
    )
    if existing is not None:
        return
    rendered = finalize_preview(kind, version.id)
    if rendered is None:
        return
    preview_kind, storage_ref = rendered
    session.add(
        PreviewArtifact(
            **{f"{kind}_version_id": version.id},
            kind=PreviewKind(preview_kind),
            storage_ref=storage_ref,
        )
    )
    session.flush()


def _publish(
    make_session: SessionFactory,
    model: type,
    kind: str,
    version_id: int,
    actor_id: int,
    rationale: str,
    finalize_preview: PreviewFinalizer | None = None,
) -> PublishResult:
    with make_session() as session, session.begin():
        version = _get(session, model, version_id, kind)
        _require_status(version, VersionStatus.draft, NOT_DRAFT, "publish")
        school_id, classroom_id = _scope_of(version, kind)
        _check_actor(session, actor_id, school_id, classroom_id)
        _check_approved(session, version, kind)
        {"asset": _check_asset_publishable, "stage": _check_stage_publishable,
         "lesson": _check_lesson_publishable}[kind](session, version)
        version.status = VersionStatus.published
        if kind == "lesson":
            _stamp_live(version)
        event = _record_event(
            session, version, kind, PublishAction.published, actor_id, rationale
        )
        if kind in ("asset", "stage") and finalize_preview is not None:
            _finalize_preview(session, kind, version, finalize_preview)
        return PublishResult(kind, version.id, version.version_no,
                             version.status.value, (event.id,))


def _scope_of(version, kind: str) -> tuple[int | None, int | None]:
    """Return (school_id, classroom_id) owning the version graph."""
    if kind == "asset":
        return version.asset.school_id, None
    lesson = version.lesson if kind == "lesson" else version.stage.lesson
    return lesson.school_id, lesson.classroom_id


def publish_asset_version(
    make_session: SessionFactory,
    version_id: int,
    actor_id: int,
    rationale: str,
    finalize_preview: PreviewFinalizer | None = None,
) -> PublishResult:
    """Publish an approved draft asset version (challenge goals required).

    When ``finalize_preview`` is given, its rendered artifact is pinned
    to the version in the same transaction (SCRUM-28).
    """
    return _publish(
        make_session, AssetVersion, "asset", version_id, actor_id, rationale,
        finalize_preview,
    )


def publish_stage_version(
    make_session: SessionFactory,
    version_id: int,
    actor_id: int,
    rationale: str,
    finalize_preview: PreviewFinalizer | None = None,
) -> PublishResult:
    """Publish an approved draft stage version (asset uses must be live).

    When ``finalize_preview`` is given, its rendered artifact is pinned
    to the version in the same transaction (SCRUM-28).
    """
    return _publish(
        make_session, StageVersion, "stage", version_id, actor_id, rationale,
        finalize_preview,
    )


def publish_lesson_version(
    make_session: SessionFactory, version_id: int, actor_id: int, rationale: str
) -> PublishResult:
    """Publish an approved draft lesson version (composition must be live)."""
    return _publish(
        make_session, LessonVersion, "lesson", version_id, actor_id, rationale
    )


# ---------------------------------------------------------------------------
# Rollback and retire
# ---------------------------------------------------------------------------


def _live_version(session: Session, model: type, version, kind: str):
    """Latest published version of the same identity and scope."""
    query = select(model).where(model.status == VersionStatus.published)
    if kind == "asset":
        query = query.where(model.asset_id == version.asset_id)
    elif kind == "stage":
        query = query.where(model.stage_id == version.stage_id)
    else:
        query = query.where(
            model.lesson_id == version.lesson_id,
            model.student_scope_id == version.student_scope_id,
        )
    return session.scalar(
        query.order_by(desc(model.version_no), desc(model.id)).limit(1)
    )


def _rollback(
    make_session: SessionFactory,
    model: type,
    kind: str,
    version_id: int,
    actor_id: int,
    rationale: str,
) -> PublishResult:
    with make_session() as session, session.begin():
        target = _get(session, model, version_id, kind)
        _require_status(target, VersionStatus.retired, NOT_RETIRED, "roll back to")
        school_id, classroom_id = _scope_of(target, kind)
        _check_actor(session, actor_id, school_id, classroom_id)
        current = _live_version(session, model, target, kind)
        if current is None:
            raise PublicationError(
                NOTHING_LIVE, "No live version to roll back from."
            )
        current.status = VersionStatus.retired
        demoted = _record_event(
            session, current, kind, PublishAction.retired, actor_id,
            f"Demoted by rollback to version {target.version_no}: {rationale}",
        )
        target.status = VersionStatus.published
        if kind == "lesson":
            _stamp_live(target)
        restored = _record_event(
            session, target, kind, PublishAction.rolled_back, actor_id, rationale
        )
        return PublishResult(kind, target.id, target.version_no,
                             target.status.value, (demoted.id, restored.id))


def rollback_asset_version(
    make_session: SessionFactory, version_id: int, actor_id: int, rationale: str
) -> PublishResult:
    """Restore a retired asset version to live, demoting the current one."""
    return _rollback(
        make_session, AssetVersion, "asset", version_id, actor_id, rationale
    )


def rollback_stage_version(
    make_session: SessionFactory, version_id: int, actor_id: int, rationale: str
) -> PublishResult:
    """Restore a retired stage version to live, demoting the current one."""
    return _rollback(
        make_session, StageVersion, "stage", version_id, actor_id, rationale
    )


def rollback_lesson_version(
    make_session: SessionFactory, version_id: int, actor_id: int, rationale: str
) -> PublishResult:
    """Restore a retired lesson version to live, demoting the current one."""
    return _rollback(
        make_session, LessonVersion, "lesson", version_id, actor_id, rationale
    )


def _retire(
    make_session: SessionFactory,
    model: type,
    kind: str,
    version_id: int,
    actor_id: int,
    rationale: str,
) -> PublishResult:
    with make_session() as session, session.begin():
        version = _get(session, model, version_id, kind)
        _require_status(version, VersionStatus.published, NOT_PUBLISHED, "retire")
        school_id, classroom_id = _scope_of(version, kind)
        _check_actor(session, actor_id, school_id, classroom_id)
        version.status = VersionStatus.retired
        event = _record_event(
            session, version, kind, PublishAction.retired, actor_id, rationale
        )
        return PublishResult(kind, version.id, version.version_no,
                             version.status.value, (event.id,))


def retire_asset_version(
    make_session: SessionFactory, version_id: int, actor_id: int, rationale: str
) -> PublishResult:
    """Take a live asset version out of service."""
    return _retire(
        make_session, AssetVersion, "asset", version_id, actor_id, rationale
    )


def retire_stage_version(
    make_session: SessionFactory, version_id: int, actor_id: int, rationale: str
) -> PublishResult:
    """Take a live stage version out of service."""
    return _retire(
        make_session, StageVersion, "stage", version_id, actor_id, rationale
    )


def retire_lesson_version(
    make_session: SessionFactory, version_id: int, actor_id: int, rationale: str
) -> PublishResult:
    """Take a live lesson version out of service."""
    return _retire(
        make_session, LessonVersion, "lesson", version_id, actor_id, rationale
    )


# ---------------------------------------------------------------------------
# Serve-time resolution
# ---------------------------------------------------------------------------


def resolve_current_lesson_version(
    session: Session, lesson_id: int, student_id: int | None
) -> LessonVersion | None:
    """Return the live lesson version a student should be served.

    A published personal variant (scoped to the student) wins over the
    published class default; ties break on the highest version number.
    """
    if student_id is not None:
        personal = session.scalar(
            select(LessonVersion)
            .where(
                LessonVersion.lesson_id == lesson_id,
                LessonVersion.status == VersionStatus.published,
                LessonVersion.student_scope_id == student_id,
            )
            .order_by(desc(LessonVersion.version_no), desc(LessonVersion.id))
            .limit(1)
        )
        if personal is not None:
            return personal
    return session.scalar(
        select(LessonVersion)
        .where(
            LessonVersion.lesson_id == lesson_id,
            LessonVersion.status == VersionStatus.published,
            LessonVersion.student_scope_id.is_(None),
        )
        .order_by(desc(LessonVersion.version_no), desc(LessonVersion.id))
        .limit(1)
    )
