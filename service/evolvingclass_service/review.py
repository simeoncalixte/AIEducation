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
    AssetUse,
    AssetVersion,
    Decision,
    Goal,
    GoalMentalModel,
    GoalMisconception,
    LessonVersion,
    LessonVersionStage,
    StageVersion,
    UserRole,
    VersionStatus,
)
from sqlalchemy import func, select

from .errors import (
    FORBIDDEN,
    INVALID_EDIT,
    NOT_FOUND,
    NOT_PUBLISHED,
    PublicationError,
)
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


def _clean_uses(uses) -> list[dict]:
    """Validate a full ordered use list; positions come from order."""
    if not isinstance(uses, list):
        raise PublicationError(
            INVALID_EDIT, "Stage uses must be a list.")
    cleaned = []
    for entry in uses:
        if not isinstance(entry, dict):
            raise PublicationError(
                INVALID_EDIT, "Each use needs an asset version and a role.")
        asset_version_id = entry.get("asset_version_id")
        if (
            not isinstance(asset_version_id, int)
            or isinstance(asset_version_id, bool)
        ):
            raise PublicationError(
                INVALID_EDIT, "Each use needs an integer asset version id.")
        role = entry.get("role")
        if not isinstance(role, str) or not role.strip():
            raise PublicationError(
                INVALID_EDIT, "Each use needs a non-blank role.")
        overrides = entry.get("param_overrides", {})
        if not isinstance(overrides, dict):
            raise PublicationError(
                INVALID_EDIT, "Use param_overrides must be an object.")
        cleaned.append({
            "asset_version_id": asset_version_id,
            "role": role.strip(),
            "param_overrides": dict(overrides),
        })
    return cleaned


def _clean_pins(pins) -> list[dict]:
    """Validate a full ordered pin list; positions come from order."""
    if not isinstance(pins, list):
        raise PublicationError(
            INVALID_EDIT, "Lesson composition must be a list.")
    cleaned = []
    seen: set[int] = set()
    for entry in pins:
        if not isinstance(entry, dict):
            raise PublicationError(
                INVALID_EDIT, "Each pin needs a stage version.")
        stage_version_id = entry.get("stage_version_id")
        if (
            not isinstance(stage_version_id, int)
            or isinstance(stage_version_id, bool)
        ):
            raise PublicationError(
                INVALID_EDIT, "Each pin needs an integer stage version id.")
        if stage_version_id in seen:
            raise PublicationError(
                INVALID_EDIT,
                f"Stage version {stage_version_id} is pinned twice.")
        seen.add(stage_version_id)
        required = entry.get("required", True)
        if not isinstance(required, bool):
            raise PublicationError(
                INVALID_EDIT, "Pin 'required' must be true or false.")
        cleaned.append({
            "stage_version_id": stage_version_id,
            "required": required,
        })
    return cleaned


def update_stage_uses(
    make_session: SessionFactory,
    version_id: int,
    actor_id: int,
    uses: list[dict],
) -> None:
    """Replace a draft stage's ordered asset uses (SCRUM-33)."""
    cleaned = _clean_uses(uses)
    with make_session() as session, session.begin():
        version = session.get(StageVersion, version_id)
        if version is None:
            raise PublicationError(
                NOT_FOUND, f"Unknown stage version {version_id}.")
        _check_role(session, actor_id)
        ensure_draft(version)
        for entry in cleaned:
            if (
                session.get(AssetVersion, entry["asset_version_id"])
                is None
            ):
                raise PublicationError(
                    NOT_FOUND,
                    f"Unknown asset version "
                    f"{entry['asset_version_id']}.",
                )
        for old in list(version.asset_uses):
            session.delete(old)
        session.flush()
        for position, entry in enumerate(cleaned, start=1):
            session.add(AssetUse(
                asset_version_id=entry["asset_version_id"],
                stage_version_id=version.id,
                position=position,
                role=entry["role"],
                param_overrides=entry["param_overrides"],
            ))


def update_lesson_composition(
    make_session: SessionFactory,
    version_id: int,
    actor_id: int,
    pins: list[dict],
) -> None:
    """Replace a draft lesson's ordered composition pins (SCRUM-33)."""
    cleaned = _clean_pins(pins)
    with make_session() as session, session.begin():
        version = session.get(LessonVersion, version_id)
        if version is None:
            raise PublicationError(
                NOT_FOUND, f"Unknown lesson version {version_id}.")
        _check_role(session, actor_id)
        ensure_draft(version)
        for entry in cleaned:
            if (
                session.get(StageVersion, entry["stage_version_id"])
                is None
            ):
                raise PublicationError(
                    NOT_FOUND,
                    f"Unknown stage version "
                    f"{entry['stage_version_id']}.",
                )
        for old in list(version.composition):
            session.delete(old)
        session.flush()
        for position, entry in enumerate(cleaned, start=1):
            session.add(LessonVersionStage(
                lesson_version_id=version.id,
                stage_version_id=entry["stage_version_id"],
                position=position,
                required=entry["required"],
            ))


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
            carried = Goal(
                challenge_version_id=draft.id,
                key=goal.key,
                rule=dict(goal.rule or {}),
                evaluation=goal.evaluation,
                rubric=goal.rubric,
                template_ref=goal.template_ref,
            )
            session.add(carried)
            session.flush()
            for model in goal.mental_models:
                session.add(GoalMentalModel(
                    goal_id=carried.id,
                    mental_model_id=model.id,
                ))
            for misconception in goal.probed_misconceptions:
                session.add(GoalMisconception(
                    goal_id=carried.id,
                    misconception_id=misconception.id,
                ))
        session.flush()
        assert draft.id is not None
        return draft.id
