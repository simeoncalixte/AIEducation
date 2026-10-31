"""Review actions: approve / reject / edit draft proposals.

Approvals and edits are the review half of the publication workflow:
teachers record decisions on drafts here, and the publication
transaction (publication.py) consumes the latest approval when a draft
is published. Both entry points enforce the publisher role and the
draft freeze guard inside one transaction.
"""

from __future__ import annotations

from DataModels import (
    AppUser,
    Approval,
    AssetTag,
    AssetVersion,
    Decision,
    Goal,
    LessonVersion,
    StageVersion,
    UserRole,
    VersionStatus,
)
from sqlalchemy import func, select

from .errors import FORBIDDEN, NOT_FOUND, NOT_PUBLISHED, PublicationError
from .publication import SessionFactory, ensure_draft

_MODELS = {
    "asset": AssetVersion,
    "stage": StageVersion,
    "lesson": LessonVersion,
}

_PUBLISHERS = frozenset({UserRole.teacher, UserRole.admin})


def _check_role(session, actor_id: int) -> None:
    actor = session.get(AppUser, actor_id)
    if actor is None:
        raise PublicationError(NOT_FOUND, f"Unknown actor {actor_id}.")
    if actor.role not in _PUBLISHERS:
        raise PublicationError(
            FORBIDDEN,
            f"Role {actor.role.value} may not review; teacher or admin required.",
        )


def record_approval(
    make_session: SessionFactory,
    kind: str,
    version_id: int,
    actor_id: int,
    decision: Decision,
    rationale: str,
) -> int:
    """Append an approval decision to a draft version. Returns approval id."""
    model = _MODELS[kind]
    with make_session() as session, session.begin():
        version = session.get(model, version_id)
        if version is None:
            raise PublicationError(NOT_FOUND, f"Unknown {kind} version {version_id}.")
        _check_role(session, actor_id)
        ensure_draft(version)
        approval = Approval(
            **{f"{kind}_version_id": version_id},
            actor_id=actor_id,
            decision=decision,
            rationale=rationale,
        )
        session.add(approval)
        session.flush()
        assert approval.id is not None
        return approval.id


def update_draft(
    make_session: SessionFactory,
    kind: str,
    version_id: int,
    actor_id: int,
    rationale: str | None = None,
    content_ref: str | None = None,
) -> None:
    """Edit mutable draft fields (rationale; content_ref for assets)."""
    model = _MODELS[kind]
    with make_session() as session, session.begin():
        version = session.get(model, version_id)
        if version is None:
            raise PublicationError(NOT_FOUND, f"Unknown {kind} version {version_id}.")
        _check_role(session, actor_id)
        ensure_draft(version)
        if rationale is not None:
            version.rationale = rationale
        if content_ref is not None:
            if kind != "asset":
                raise PublicationError(
                    FORBIDDEN, "Only asset versions carry a content_ref."
                )
            version.content_ref = content_ref


def revise_asset_version(
    make_session: SessionFactory,
    version_id: int,
    actor_id: int,
    rationale: str,
) -> int:
    """Draft a new asset version revising a published or retired one.

    Content, objectives, params, tags, and goals carry over; the new
    draft names its source in its rationale, and existing pins keep
    pointing at the revised version. Returns the new version id.
    """
    with make_session() as session, session.begin():
        source = session.get(AssetVersion, version_id)
        if source is None:
            raise PublicationError(
                NOT_FOUND, f"Unknown asset version {version_id}.")
        _check_role(session, actor_id)
        if source.status is VersionStatus.draft:
            raise PublicationError(
                NOT_PUBLISHED,
                f"Only published or retired versions can be revised; "
                f"version {version_id} is still a draft.",
            )
        version_no = (session.scalar(
            select(func.max(AssetVersion.version_no)).where(
                AssetVersion.asset_id == source.asset_id)
        ) or 0) + 1
        draft = AssetVersion(
            asset_id=source.asset_id,
            version_no=version_no,
            status=VersionStatus.draft,
            rationale=f"Revision of v{source.version_no}: {rationale}",
            objective_refs=list(source.objective_refs or []),
            content_ref=source.content_ref,
            param_schema=dict(source.param_schema or {}),
        )
        session.add(draft)
        session.flush()
        for tag in source.tags:
            session.add(AssetTag(
                asset_version_id=draft.id,
                taxonomy=tag.taxonomy,
                value=tag.value,
            ))
        for goal in source.goals:
            session.add(Goal(
                challenge_version_id=draft.id,
                key=goal.key,
                rule=dict(goal.rule or {}),
                evaluation=goal.evaluation,
                rubric=goal.rubric,
                template_ref=goal.template_ref,
            ))
        session.flush()
        assert draft.id is not None
        return draft.id
