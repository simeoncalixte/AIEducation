"""View models for the review queues.

Every builder takes an open Session and returns plain dicts/lists, so
templates never touch detached ORM instances.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from DataModels import (
    Approval,
    AssetVersion,
    Decision,
    LessonVersion,
    PublishEvent,
    StageVersion,
    VersionStatus,
)

KINDS = ("asset", "stage", "lesson")

# Pilot low-impact bar: an asset flags when its latest rollup's mastery
# falls below this. The impact formula and retirement thresholds move to
# analytics.md post-pilot; the flag always shows its evidence.
LOW_MASTERY_THRESHOLD = 0.5

_MODELS = {
    "asset": AssetVersion,
    "stage": StageVersion,
    "lesson": LessonVersion,
}


def _dump(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def _field(name: str, old: Any, new: Any) -> dict:
    return {"field": name, "old": _dump(old), "new": _dump(new),
            "changed": old != new}


def _latest_decision(session: Session, kind: str, version_id: int) -> str:
    column = getattr(Approval, f"{kind}_version_id")
    latest = session.scalar(
        select(Approval)
        .where(column == version_id)
        .order_by(desc(Approval.decided_at), desc(Approval.id))
        .limit(1)
    )
    if latest is None:
        return "pending"
    return latest.decision.value


# ---------------------------------------------------------------------------
# Queues
# ---------------------------------------------------------------------------


def _title_of(version, kind: str) -> str:
    if kind == "asset":
        return f"{version.asset.title} ({version.asset.kind.value})"
    if kind == "stage":
        return f"{version.stage.lesson.title} / {version.stage.title}"
    scope = "class default"
    if version.student_scope_id is not None:
        scope = f"personal: {version.scope_student.display_name}"
    return f"{version.lesson.title} [{scope}]"


def queue_rows(session: Session) -> dict[str, list[dict]]:
    """One row per version that needs review, grouped by level.

    Drafts are the review workload; published and retired versions are
    included so teachers can retire live work or roll back to it.
    """
    queues: dict[str, list[dict]] = {}
    for kind in KINDS:
        model = _MODELS[kind]
        versions = list(session.scalars(
            select(model).order_by(model.id)
        ))
        rows = []
        for version in versions:
            rows.append({
                "id": version.id,
                "title": _title_of(version, kind),
                "version_no": version.version_no,
                "status": version.status.value,
                "rationale": (version.rationale or "")[:120],
                "decision": _latest_decision(session, kind, version.id),
                "low_impact": (kind == "asset" and _low_impact(
                    session, version.asset_id)),
            })
        # Drafts first, then the rest, newest identity last touched first.
        rows.sort(key=lambda r: (r["status"] != VersionStatus.draft.value,
                                 -r["id"]))
        queues[kind] = rows
    return queues


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


def _prior(session: Session, kind: str, version):
    model = _MODELS[kind]
    identity = {"asset": "asset_id", "stage": "stage_id",
                "lesson": "lesson_id"}[kind]
    query = select(model).where(
        getattr(model, identity) == getattr(version, identity),
        model.version_no < version.version_no,
    )
    if kind == "lesson":
        if version.student_scope_id is None:
            query = query.where(model.student_scope_id.is_(None))
        else:
            query = query.where(
                model.student_scope_id == version.student_scope_id
            )
    return session.scalar(
        query.order_by(desc(model.version_no)).limit(1)
    )


def _tag_list(version: AssetVersion) -> list[str]:
    return sorted(f"{t.taxonomy.value}:{t.value}" for t in version.tags)


def _goal_list(version: AssetVersion) -> list[str]:
    return sorted(f"{g.key} [{g.evaluation.value}]" for g in version.goals)


def _use_list(version: StageVersion) -> list[str]:
    return sorted(
        f"{u.asset_version.asset.title} v{u.asset_version.version_no} "
        f"({u.role}, {u.asset_version.status.value})"
        for u in version.asset_uses
    )


def _composition_list(version: LessonVersion) -> list[str]:
    return [
        f"{link.position}. {link.stage_version.stage.title} "
        f"v{link.stage_version.version_no} "
        f"({link.stage_version.status.value}"
        f"{'' if link.required else ', optional'})"
        for link in sorted(version.composition, key=lambda l: l.position)
    ]


def _model_list(version: LessonVersion) -> list[str]:
    return [m.statement for m in
            sorted(version.mental_models, key=lambda m: m.position)]


def _diff(kind: str, version, prior) -> list[dict]:
    old = prior
    rows = [_field("rationale", old.rationale if old else None,
                   version.rationale)]
    if kind == "asset":
        assert isinstance(version, AssetVersion)
        rows.append(_field("objective_refs",
                           old.objective_refs if old else None,
                           version.objective_refs))
        rows.append(_field("content_ref",
                           old.content_ref if old else None,
                           version.content_ref))
        rows.append(_field("param_schema",
                           old.param_schema if old else None,
                           version.param_schema))
        rows.append(_field("tags",
                           _tag_list(old) if old else None,
                           _tag_list(version)))
        rows.append(_field("goals",
                           _goal_list(old) if old else None,
                           _goal_list(version)))
    elif kind == "stage":
        assert isinstance(version, StageVersion)
        rows.append(_field("asset_uses",
                           _use_list(old) if old else None,
                           _use_list(version)))
    else:
        assert isinstance(version, LessonVersion)
        rows.append(_field("objective_refs",
                           old.objective_refs if old else None,
                           version.objective_refs))
        rows.append(_field("composition",
                           _composition_list(old) if old else None,
                           _composition_list(version)))
        rows.append(_field("mental_models",
                           _model_list(old) if old else None,
                           _model_list(version)))
    return rows


def _coverage(session: Session, kind: str, version) -> dict:
    snapshot = version.directive_snapshot or {}
    snap_ids = set()
    snap_rows = []
    raw = snapshot.get("directives", []) if isinstance(snapshot, dict) else []
    for entry in raw:
        if isinstance(entry, dict) and "id" in entry:
            snap_ids.add(entry["id"])
            snap_rows.append({"id": entry["id"],
                              "focus": str(entry.get("focus", ""))})
    lesson_rows: list[dict] = []
    if kind == "lesson":
        for directive in version.lesson.directives:
            lesson_rows.append({
                "id": directive.id,
                "kind": directive.kind.value,
                "focus": directive.focus,
                "active": directive.active,
                "covered": directive.id in snap_ids,
            })
    run = version.generation_run
    return {
        "snapshot_present": bool(snapshot),
        "snapshot_directives": snap_rows,
        "brief": snapshot.get("brief", "") if isinstance(snapshot, dict) else "",
        "lesson_directives": lesson_rows,
        "generation_run": None if run is None else {
            "id": run.id, "agent": run.agent_ref, "model": run.model_ref,
            "status": run.status.value,
        },
    }


def _latest_mastery(session: Session, asset_version_id: int) -> str:
    from DataModels import ImpactRollup

    rollup = session.scalar(
        select(ImpactRollup)
        .where(ImpactRollup.asset_version_id == asset_version_id)
        .order_by(desc(ImpactRollup.id))
        .limit(1)
    )
    if rollup is None:
        return "—"
    return f"{rollup.mastery:.2f} (n={rollup.sample_size})"


def _latest_asset_rollup(session: Session, asset_id: int):
    """Newest rollup across an asset's versions, or None."""
    from DataModels import AssetVersion, ImpactRollup

    return session.scalar(
        select(ImpactRollup)
        .join(AssetVersion,
              ImpactRollup.asset_version_id == AssetVersion.id)
        .where(AssetVersion.asset_id == asset_id)
        .order_by(desc(ImpactRollup.id))
        .limit(1)
    )


def _low_impact(session: Session, asset_id: int) -> bool:
    rollup = _latest_asset_rollup(session, asset_id)
    return rollup is not None and rollup.mastery < LOW_MASTERY_THRESHOLD


def _reuse_matches(session: Session, version: AssetVersion) -> list[dict]:
    """Published same-kind versions that could have been reused instead."""
    from DataModels import Asset, AssetVisibility

    candidates = list(session.scalars(
        select(AssetVersion)
        .join(Asset, AssetVersion.asset_id == Asset.id)
        .where(
            Asset.kind == version.asset.kind,
            AssetVersion.status == VersionStatus.published,
            AssetVersion.asset_id != version.asset_id,
            ((Asset.school_id == version.asset.school_id)
             | (Asset.visibility == AssetVisibility.shared)),
        )
        .order_by(desc(AssetVersion.id))
        .limit(5)
    ))
    return [{
        "title": c.asset.title,
        "version_no": c.version_no,
        "id": c.id,
        "mastery": _latest_mastery(session, c.id),
    } for c in candidates]


def _impact_rows(session: Session, version: AssetVersion) -> list[dict]:
    from DataModels import ImpactRollup

    rollups = list(session.scalars(
        select(ImpactRollup)
        .join(AssetVersion, ImpactRollup.asset_version_id == AssetVersion.id)
        .where(AssetVersion.asset_id == version.asset_id)
        .order_by(desc(AssetVersion.version_no), desc(ImpactRollup.id))
    ))
    rows = []
    for rollup in rollups:
        asset_v = next(v for v in version.asset.versions
                       if v.id == rollup.asset_version_id)
        rows.append({
            "version_no": asset_v.version_no,
            "window": rollup.window,
            "mastery": f"{rollup.mastery:.2f}",
            "completion": f"{rollup.completion:.2f}",
            "enjoyment": f"{rollup.enjoyment:.2f}",
            "sample_size": rollup.sample_size,
            "formula": rollup.formula_version,
            "cohort": rollup.cohort or "—",
            "uncertainty": ("—" if rollup.uncertainty is None
                            else f"{rollup.uncertainty:.2f}"),
            "low": rollup.mastery < LOW_MASTERY_THRESHOLD,
        })
    return rows


def _usage_rows(version: AssetVersion) -> list[dict]:
    """Stage/lesson/challenge versions consuming this asset version."""
    rows = []
    for use in sorted(version.uses, key=lambda u: u.id):
        if use.stage_version is not None:
            consumer = use.stage_version
            label = (f"{consumer.stage.lesson.title} / "
                     f"{consumer.stage.title}")
            kind, link = "stage", "stage"
        elif use.lesson_version is not None:
            consumer = use.lesson_version
            label = consumer.lesson.title
            kind, link = "lesson", "lesson"
        else:
            consumer = use.challenge_version
            label = consumer.asset.title
            kind, link = "challenge", "asset"
        rows.append({
            "consumer": label,
            "kind": kind,
            "link_kind": link,
            "version_id": consumer.id,
            "version_no": consumer.version_no,
            "status": consumer.status.value,
            "role": use.role,
        })
    return rows


def _use_rows(session: Session, version: StageVersion) -> list[dict]:
    return [{
        "asset": u.asset_version.asset.title,
        "kind": u.asset_version.asset.kind.value,
        "asset_version_id": u.asset_version_id,
        "version_no": u.asset_version.version_no,
        "status": u.asset_version.status.value,
        "role": u.role,
        "mastery": _latest_mastery(session, u.asset_version_id),
        "param_overrides": dict(u.param_overrides or {}),
    } for u in sorted(version.asset_uses, key=lambda u: u.position)]


def _preview_rows(version) -> list[dict]:
    """Preview artifacts pinned to this exact version, oldest first."""
    return [{
        "kind": p.kind.value,
        "storage_ref": p.storage_ref,
        "rendered_at": str(p.rendered_at),
    } for p in sorted(version.previews, key=lambda p: p.id)]


def _composition_rows(version: LessonVersion) -> list[dict]:
    return [{
        "position": link.position,
        "stage": link.stage_version.stage.title,
        "version_no": link.stage_version.version_no,
        "stage_version_id": link.stage_version_id,
        "status": link.stage_version.status.value,
        "required": link.required,
        "uses": len(link.stage_version.asset_uses),
    } for link in sorted(version.composition, key=lambda l: l.position)]


def _stage_goal_rows(version: StageVersion) -> list[dict]:
    """Challenge goals reachable from this stage's uses, by position."""
    from DataModels import AssetKind

    rows = []
    for use in sorted(version.asset_uses, key=lambda u: u.position):
        candidate = use.asset_version
        if candidate.asset.kind is not AssetKind.challenge:
            continue
        rows.append({
            "challenge": candidate.asset.title,
            "challenge_version_id": candidate.id,
            "version_no": candidate.version_no,
            "goals": [{
                "key": goal.key,
                "evaluation": goal.evaluation.value,
                "template_ref": goal.template_ref,
                "rule": dict(goal.rule or {}),
                "rubric": (
                    dict(goal.rubric)
                    if goal.rubric is not None else None
                ),
                "models": [m.statement for m in sorted(
                    goal.mental_models, key=lambda m: m.position)],
                "probes": [m.description for m in sorted(
                    goal.probed_misconceptions, key=lambda m: m.id)],
            } for goal in sorted(candidate.goals,
                                 key=lambda g: g.key)],
        })
    return rows


def _lesson_context_rows(version: StageVersion) -> list[dict]:
    """Lesson versions pinning this stage, with models + composition."""
    rows = []
    for link in sorted(version.lesson_links,
                       key=lambda l: l.lesson_version_id):
        lesson_version = link.lesson_version
        scope = "class default"
        if lesson_version.student_scope_id is not None:
            scope = (
                "personal: "
                f"{lesson_version.scope_student.display_name}"
            )
        rows.append({
            "lesson": lesson_version.lesson.title,
            "lesson_version_id": lesson_version.id,
            "version_no": lesson_version.version_no,
            "status": lesson_version.status.value,
            "scope": scope,
            "position": link.position,
            "required": link.required,
            "models": [m.statement for m in sorted(
                lesson_version.mental_models,
                key=lambda m: m.position)],
            "composition": _composition_rows(lesson_version),
        })
    return rows


def _audit(session: Session, kind: str, version_id: int) -> dict:
    approvals = list(session.scalars(
        select(Approval)
        .where(getattr(Approval, f"{kind}_version_id") == version_id)
        .order_by(Approval.decided_at, Approval.id)
    ))
    events = list(session.scalars(
        select(PublishEvent)
        .where(getattr(PublishEvent, f"{kind}_version_id") == version_id)
        .order_by(PublishEvent.id)
    ))
    return {
        "approvals": [{
            "actor": a.actor.display_name,
            "decision": a.decision.value,
            "rationale": a.rationale,
            "at": str(a.decided_at),
        } for a in approvals],
        "events": [{
            "action": e.action.value,
            "actor": e.actor.display_name,
            "rationale": e.rationale,
            "at": str(e.created_at),
        } for e in events],
    }


def detail(session: Session, kind: str, version_id: int) -> dict | None:
    """Full review dossier for one version, or None when unknown."""
    model = _MODELS[kind]
    version = session.get(model, version_id)
    if version is None:
        return None
    prior = _prior(session, kind, version)
    dossier: dict = {
        "kind": kind,
        "id": version.id,
        "title": _title_of(version, kind),
        "version_no": version.version_no,
        "status": version.status.value,
        "rationale": version.rationale,
        "prior_version_no": prior.version_no if prior else None,
        "diff": _diff(kind, version, prior),
        "coverage": _coverage(session, kind, version),
        "decision": _latest_decision(session, kind, version.id),
        "audit": _audit(session, kind, version.id),
        "reuse": [],
        "impact": [],
        "usage": [],
        "previews": [],
        "low_impact": False,
        "uses": [],
        "composition": [],
        "goals": [],
        "lessons": [],
    }
    if kind == "asset":
        assert isinstance(version, AssetVersion)
        dossier["content_ref"] = version.content_ref
        dossier["reuse"] = _reuse_matches(session, version)
        dossier["impact"] = _impact_rows(session, version)
        dossier["usage"] = _usage_rows(version)
        dossier["previews"] = _preview_rows(version)
        dossier["low_impact"] = _low_impact(session, version.asset_id)
    elif kind == "stage":
        assert isinstance(version, StageVersion)
        dossier["uses"] = _use_rows(session, version)
        dossier["goals"] = _stage_goal_rows(version)
        dossier["lessons"] = _lesson_context_rows(version)
        dossier["previews"] = _preview_rows(version)
    else:
        assert isinstance(version, LessonVersion)
        dossier["composition"] = _composition_rows(version)
    return dossier


def lesson_list(session: Session) -> list[dict]:
    """Lessons a teacher can brief, with draft/published version counts."""
    from sqlalchemy import func

    from DataModels import Lesson, LessonVersion

    lessons = list(session.scalars(
        select(Lesson).order_by(Lesson.id)
    ))
    counts: dict[tuple[int, str], int] = {}
    for lesson_id, status, count in session.execute(
        select(LessonVersion.lesson_id, LessonVersion.status,
               func.count())
        .group_by(LessonVersion.lesson_id, LessonVersion.status)
    ):
        counts[(lesson_id, status.value)] = count
    return [{
        "id": lesson.id,
        "title": lesson.title,
        "subject": lesson.subject,
        "classroom": lesson.classroom.name if lesson.classroom else "—",
        "drafts": counts.get((lesson.id, VersionStatus.draft.value), 0),
        "published": counts.get(
            (lesson.id, VersionStatus.published.value), 0),
    } for lesson in lessons]


def roster(session: Session, lesson_id: int) -> list[dict]:
    """Students of the lesson classroom available for targeting."""
    from DataModels import AppUser, Classroom, Lesson, Membership, \
        MembershipStatus, UserRole

    lesson = session.get(Lesson, lesson_id)
    if lesson is None:
        return []
    query = (
        select(AppUser)
        .join(Membership, Membership.user_id == AppUser.id)
        .outerjoin(Classroom, Membership.classroom_id == Classroom.id)
        .where(
            AppUser.role == UserRole.student,
            Membership.status == MembershipStatus.active,
        )
    )
    if lesson.classroom_id is not None:
        query = query.where(
            Membership.classroom_id == lesson.classroom_id)
    else:
        query = query.where(
            (Membership.school_id == lesson.school_id)
            | (Classroom.school_id == lesson.school_id)
        )
    students = list(session.scalars(
        query.order_by(AppUser.display_name, AppUser.id)))
    seen: set[int] = set()
    out = []
    for student in students:
        if student.id not in seen:
            seen.add(student.id)
            out.append({"id": student.id, "name": student.display_name})
    return out


def _scope_label(directive) -> str:
    if directive.student_id is None:
        return "Class-wide"
    return directive.student.display_name


def brief_context(session: Session, lesson_id: int) -> dict | None:
    """Lesson plus its directives as context for the brief form."""
    from DataModels import Lesson

    lesson = session.get(Lesson, lesson_id)
    if lesson is None:
        return None
    return {
        "id": lesson.id,
        "title": lesson.title,
        "subject": lesson.subject,
        "classroom": lesson.classroom.name if lesson.classroom else "—",
        "directives": [{
            "id": d.id,
            "kind": d.kind.value,
            "scope": _scope_label(d),
            "focus": d.focus,
            "priority": d.priority,
            "active": d.active,
        } for d in sorted(lesson.directives, key=lambda d: d.id)],
        "roster": roster(session, lesson_id),
    }


def directive_detail(session: Session, directive_id: int) -> dict | None:
    """One directive with editable fields split for the edit form."""
    from DataModels import Directive

    directive = session.get(Directive, directive_id)
    if directive is None:
        return None
    constraints = directive.constraints or {}
    return {
        "id": directive.id,
        "lesson_id": directive.lesson_id,
        "kind": directive.kind.value,
        "scope": _scope_label(directive),
        "focus": directive.focus,
        "must_include": ", ".join(constraints.get("must_include", [])),
        "must_avoid": ", ".join(constraints.get("must_avoid", [])),
        "priority": directive.priority,
        "active": directive.active,
    }


def assignment_options(session: Session) -> dict:
    """Lessons, classrooms, and students for the assignment form."""
    from DataModels import AppUser, Classroom, Lesson, UserRole

    lessons = [{
        "id": lesson.id,
        "title": lesson.title,
        "classroom": lesson.classroom.name if lesson.classroom else "—",
    } for lesson in session.scalars(select(Lesson).order_by(Lesson.id))]
    classrooms = [{
        "id": room.id, "name": f"{room.school.name} / {room.name}",
    } for room in session.scalars(select(Classroom).order_by(Classroom.id))]
    students = [{
        "id": user.id, "name": user.display_name,
    } for user in session.scalars(
        select(AppUser).where(AppUser.role == UserRole.student)
        .order_by(AppUser.display_name, AppUser.id))]
    return {"lessons": lessons, "classrooms": classrooms,
            "students": students}


def assignment_list(session: Session) -> list[dict]:
    """Assignments with live attempt counts (pilot: unfiltered)."""
    from sqlalchemy import func

    from DataModels import Assignment, Attempt

    counts = dict(session.execute(
        select(Attempt.assignment_id, func.count())
        .group_by(Attempt.assignment_id)
    ).all())
    rows = []
    for assignment in session.scalars(
            select(Assignment).order_by(Assignment.id)):
        if assignment.student_id is not None:
            target = assignment.student.display_name
        else:
            target = assignment.classroom.name
        rows.append({
            "id": assignment.id,
            "lesson": assignment.lesson.title,
            "target": target,
            "by": assignment.assigned_by.display_name,
            "attempts": counts.get(assignment.id, 0),
        })
    return rows


def _verdict_rows(session: Session, attempt) -> list[dict]:
    from DataModels import ExperienceEvent, VerdictOverride

    rows = []
    for event in sorted(attempt.events, key=lambda e: e.id):
        if event.verb != "goal-verdict":
            continue
        override = session.scalar(
            select(VerdictOverride)
            .where(VerdictOverride.verdict_event_id == event.id)
            .order_by(desc(VerdictOverride.id))
            .limit(1)
        )
        payload = event.payload or {}
        if override is not None:
            passed: bool | None = override.corrected_passed
            score = override.corrected_score
        else:
            passed = payload.get("passed")
            score = payload.get("score")
        rows.append({
            "event_id": event.id,
            "goal": event.object_ref,
            "passed": passed,
            "score": score,
            "overridden": override is not None,
            "override_reason": override.reason if override else "",
        })
    return rows


def _flag_rows(attempt) -> list[dict]:
    return [{
        "id": event.id,
        "ref": event.object_ref,
        "note": (event.payload or {}).get("note", ""),
        "at": str(event.created_at),
    } for event in sorted(attempt.events, key=lambda e: e.id)
        if event.verb == "misconception-flagged"]


def _latest_rating(session: Session, lesson_id: int,
                   student_id: int) -> int | None:
    from DataModels import LessonVersion, Rating

    rating = session.scalar(
        select(Rating)
        .join(LessonVersion,
              Rating.lesson_version_id == LessonVersion.id)
        .where(Rating.author_id == student_id,
               LessonVersion.lesson_id == lesson_id)
        .order_by(desc(Rating.id))
        .limit(1)
    )
    return rating.score if rating else None


def _assignment_students(session: Session, assignment) -> list:
    if assignment.student_id is not None:
        return [assignment.student]
    from DataModels import AppUser, Membership, MembershipStatus, UserRole

    return list(session.scalars(
        select(AppUser)
        .join(Membership, Membership.user_id == AppUser.id)
        .where(
            Membership.classroom_id == assignment.classroom_id,
            Membership.status == MembershipStatus.active,
            AppUser.role == UserRole.student,
        )
        .order_by(AppUser.display_name, AppUser.id)
    ))


def assignment_progress(session: Session,
                        assignment_id: int) -> dict | None:
    """Live per-student progress: attempts, verdicts, flags, enjoyment."""
    from DataModels import Assignment, LessonVersion, MentalModel, \
        Misconception

    assignment = session.get(Assignment, assignment_id)
    if assignment is None:
        return None
    students = []
    for student in _assignment_students(session, assignment):
        attempts = sorted(
            (a for a in assignment.attempts if a.student_id == student.id),
            key=lambda a: a.id)
        students.append({
            "id": student.id,
            "name": student.display_name,
            "rating": _latest_rating(session, assignment.lesson_id,
                                     student.id),
            "attempts": [{
                "id": attempt.id,
                "started": str(attempt.started_at),
                "finished": (str(attempt.finished_at)
                             if attempt.finished_at else None),
                "retry_of": attempt.retry_of_id,
                "verdicts": _verdict_rows(session, attempt),
                "flags": _flag_rows(attempt),
            } for attempt in attempts],
        })
    misconceptions = [{
        "id": misc.id,
        "label": f"{misc.description} ({misc.mental_model.statement[:60]})",
    } for misc in session.scalars(
        select(Misconception)
        .join(MentalModel,
              Misconception.mental_model_id == MentalModel.id)
        .join(LessonVersion,
              MentalModel.lesson_version_id == LessonVersion.id)
        .where(LessonVersion.lesson_id == assignment.lesson_id)
        .order_by(Misconception.id)
    )]
    return {
        "id": assignment.id,
        "lesson": assignment.lesson.title,
        "target": (assignment.student.display_name
                   if assignment.student_id is not None
                   else assignment.classroom.name),
        "students": students,
        "misconceptions": misconceptions,
    }


def student_assignments(session: Session, student_id: int) -> list[dict]:
    """Assignments targeting a student, with live attempt status."""
    from DataModels import Assignment, Attempt, Membership, MembershipStatus

    rooms = list(session.scalars(
        select(Membership.classroom_id).where(
            Membership.user_id == student_id,
            Membership.status == MembershipStatus.active,
            Membership.classroom_id.is_not(None),
        )))
    rows = []
    for assignment in session.scalars(
        select(Assignment)
        .where(
            (Assignment.student_id == student_id)
            | (Assignment.classroom_id.in_(rooms) if rooms else False)
        )
        .order_by(Assignment.id)
    ):
        attempts = sorted(
            (a for a in assignment.attempts if a.student_id == student_id),
            key=lambda a: a.id)
        if not attempts:
            status = "not started"
        elif attempts[-1].finished_at is not None:
            status = "finished"
        else:
            status = "in progress"
        rows.append({
            "id": assignment.id,
            "lesson": assignment.lesson.title,
            "status": status,
            "attempts": len(attempts),
            "latest_attempt_id": attempts[-1].id if attempts else None,
        })
    return rows


def _student_in_scope(session: Session, assignment,
                      student_id: int) -> bool:
    if assignment.student_id is not None:
        return assignment.student_id == student_id
    from DataModels import Membership, MembershipStatus

    return session.scalar(
        select(Membership.id).where(
            Membership.user_id == student_id,
            Membership.classroom_id == assignment.classroom_id,
            Membership.status == MembershipStatus.active,
        )) is not None


def briefing(session: Session, assignment_id: int,
             student_id: int) -> dict | None:
    """Briefing data for one assignment, or None when inaccessible."""
    from DataModels import Assignment, Attempt
    from evolvingclass_service.publication import \
        resolve_current_lesson_version

    assignment = session.get(Assignment, assignment_id)
    if assignment is None:
        return None
    if not _student_in_scope(session, assignment, student_id):
        return None
    version = resolve_current_lesson_version(
        session, assignment.lesson_id, student_id)
    if version is None:
        return {"assignment_id": assignment.id,
                "lesson": assignment.lesson.title,
                "published": False}
    open_attempt = session.scalar(
        select(Attempt)
        .where(
            Attempt.assignment_id == assignment_id,
            Attempt.student_id == student_id,
            Attempt.finished_at.is_(None),
        )
        .order_by(Attempt.id.desc())
        .limit(1)
    )
    return {
        "assignment_id": assignment.id,
        "lesson": assignment.lesson.title,
        "published": True,
        "objectives": list(version.objective_refs or []),
        "models": [model.statement for model in sorted(
            version.mental_models, key=lambda m: m.position)],
        "stages": [link.stage_version.stage.title for link in sorted(
            version.composition, key=lambda l: l.position)],
        "open_attempt_id": open_attempt.id if open_attempt else None,
    }


def _play_challenges(pinned_version) -> list[dict]:
    from DataModels import AssetKind

    challenges = []
    for link in sorted(pinned_version.composition,
                       key=lambda l: l.position):
        uses = sorted(link.stage_version.asset_uses,
                      key=lambda u: u.position)
        guides = [{
            "name": use.asset_version.asset.title,
            "role": use.role,
        } for use in uses if use.role == "guide"]
        for use in uses:
            candidate = use.asset_version
            if candidate.asset.kind is not AssetKind.challenge:
                continue
            challenges.append({
                "challenge_version_id": candidate.id,
                "stage": link.stage_version.stage.title,
                "title": candidate.asset.title,
                "goals": sorted(goal.key for goal in candidate.goals),
                "guides": guides,
            })
    return challenges


def attempt_owner(session: Session, attempt_id: int) -> int | None:
    """Owning student id for an attempt, or None when unknown."""
    from DataModels import Attempt

    attempt = session.get(Attempt, attempt_id)
    return attempt.student_id if attempt else None


def challenge_view(session: Session, attempt_id: int,
                   index: int) -> dict | None:
    """One challenge page (1-based index), or None when invalid."""
    from DataModels import Attempt

    attempt = session.get(Attempt, attempt_id)
    if attempt is None:
        return None
    challenges = _play_challenges(attempt.pinned_lesson_version)
    if not 1 <= index <= len(challenges):
        return None
    entry = challenges[index - 1]
    answered = {
        event.object_ref for event in attempt.events
        if event.verb == "goal-attempted"
        and event.challenge_version_id == entry["challenge_version_id"]
    }
    return {
        "attempt_id": attempt.id,
        "assignment_id": attempt.assignment_id,
        "index": index,
        "total": len(challenges),
        "stage": entry["stage"],
        "title": entry["title"],
        "challenge_version_id": entry["challenge_version_id"],
        "goals": [{"key": key, "answered": key in answered}
                  for key in entry["goals"]],
        "guides": entry["guides"],
        "finished": attempt.finished_at is not None,
    }


def debrief_view(session: Session, attempt_id: int) -> dict | None:
    """Results, rating, and retry for one attempt, or None."""
    from DataModels import Attempt

    attempt = session.get(Attempt, attempt_id)
    if attempt is None:
        return None
    return {
        "attempt_id": attempt.id,
        "assignment_id": attempt.assignment_id,
        "lesson": attempt.assignment.lesson.title,
        "finished": attempt.finished_at is not None,
        "verdicts": _verdict_rows(session, attempt),
        "rating": _latest_rating(session, attempt.assignment.lesson_id,
                                 attempt.student_id),
    }


def school_status(session: Session) -> list[dict]:
    """Lesson status grouped by classroom, with version counts."""
    from sqlalchemy import func

    from DataModels import Assignment, Attempt, Classroom, Lesson, \
        LessonVersion, School

    version_counts: dict[tuple[int, str], int] = {}
    for lesson_id, status, count in session.execute(
        select(LessonVersion.lesson_id, LessonVersion.status,
               func.count())
        .group_by(LessonVersion.lesson_id, LessonVersion.status)
    ):
        version_counts[(lesson_id, status.value)] = count
    assignment_counts = dict(session.execute(
        select(Assignment.lesson_id, func.count())
        .group_by(Assignment.lesson_id)
    ).all())
    attempt_counts = dict(session.execute(
        select(Assignment.lesson_id, func.count())
        .join(Attempt, Attempt.assignment_id == Assignment.id)
        .group_by(Assignment.lesson_id)
    ).all())
    by_room: dict[str, list[dict]] = {}
    for lesson in session.scalars(select(Lesson).order_by(Lesson.id)):
        if lesson.classroom_id is not None:
            room: str = lesson.classroom.name
        else:
            school = session.get(School, lesson.school_id)
            room = f"{school.name} (school-wide)"
        by_room.setdefault(room, []).append({
            "id": lesson.id,
            "title": lesson.title,
            "subject": lesson.subject,
            "drafts": version_counts.get(
                (lesson.id, VersionStatus.draft.value), 0),
            "published": version_counts.get(
                (lesson.id, VersionStatus.published.value), 0),
            "retired": version_counts.get(
                (lesson.id, VersionStatus.retired.value), 0),
            "assignments": assignment_counts.get(lesson.id, 0),
            "attempts": attempt_counts.get(lesson.id, 0),
        })
    rooms = [{"name": room.name, "id": room.id} for room in
             session.scalars(select(Classroom).order_by(Classroom.id))]
    known = {room["name"] for room in rooms}
    ordered = [{"name": room["name"], "lessons": by_room.get(room["name"], [])}
               for room in rooms]
    ordered.extend(
        {"name": name, "lessons": lessons}
        for name, lessons in sorted(by_room.items()) if name not in known)
    return ordered


def _audit_target(session: Session, kind: str, row) -> str:
    if kind == "approval":
        if row.asset_version_id is not None:
            version = session.get(AssetVersion, row.asset_version_id)
            return (f"asset {version.asset.title} "
                    f"v{version.version_no}")
        if row.stage_version_id is not None:
            version = session.get(StageVersion, row.stage_version_id)
            return (f"stage {version.stage.title} "
                    f"v{version.version_no}")
        version = session.get(LessonVersion, row.lesson_version_id)
        return (f"lesson {version.lesson.title} "
                f"v{version.version_no}")
    if row.asset_version_id is not None:
        version = session.get(AssetVersion, row.asset_version_id)
        return (f"asset {version.asset.title} "
                f"v{version.version_no}")
    if row.stage_version_id is not None:
        version = session.get(StageVersion, row.stage_version_id)
        return (f"stage {version.stage.title} "
                f"v{version.version_no}")
    version = session.get(LessonVersion, row.lesson_version_id)
    return (f"lesson {version.lesson.title} "
            f"v{version.version_no}")


def audit_trail(session: Session, actor_id: int | None = None,
                since=None, until=None) -> list[dict]:
    """Approvals plus publish events, newest first, optionally filtered."""
    from DataModels import Approval, PublishEvent

    rows: list[dict] = []
    for approval in session.scalars(select(Approval)):
        at = approval.decided_at
        rows.append({
            "at": at, "at_text": str(at),
            "actor_id": approval.actor_id,
            "actor": approval.actor.display_name,
            "kind": "approval",
            "result": approval.decision.value,
            "target": _audit_target(session, "approval", approval),
            "rationale": approval.rationale,
        })
    for event in session.scalars(select(PublishEvent)):
        at = event.created_at
        rows.append({
            "at": at, "at_text": str(at),
            "actor_id": event.actor_id,
            "actor": event.actor.display_name,
            "kind": "publish",
            "result": event.action.value,
            "target": _audit_target(session, "publish", event),
            "rationale": event.rationale,
        })
    if actor_id is not None:
        rows = [row for row in rows if row["actor_id"] == actor_id]
    if since is not None:
        rows = [row for row in rows if row["at"] is not None
                and row["at"].date() >= since]
    if until is not None:
        rows = [row for row in rows if row["at"] is not None
                and row["at"].date() <= until]
    import datetime as _dt

    rows.sort(key=lambda row: row["at"] or _dt.datetime.min,
              reverse=True)
    for row in rows:
        del row["at"]
    return rows


def audit_actors(session: Session) -> list[dict]:
    """Users available as audit-trail actor filters."""
    from DataModels import AppUser

    return [{
        "id": user.id, "name": user.display_name, "role": user.role.value,
    } for user in session.scalars(
        select(AppUser).order_by(AppUser.display_name, AppUser.id))]


def login_choices(session: Session) -> list[dict]:
    """All users eligible to log in, teachers first (pilot login list)."""
    from DataModels import AppUser, UserRole

    users = list(session.scalars(select(AppUser).order_by(AppUser.id)))
    order = {UserRole.teacher: 0, UserRole.admin: 1, UserRole.student: 2}
    users.sort(key=lambda u: (order[u.role], u.id))
    return [{"id": u.id, "name": u.display_name, "role": u.role.value,
             "login": u.login_ref} for u in users]


def find_by_login(session: Session, login_ref: str) -> dict | None:
    """User card for a login name, or None when unknown."""
    from DataModels import AppUser

    user = session.scalar(
        select(AppUser).where(AppUser.login_ref == login_ref))
    if user is None:
        return None
    return {"id": user.id, "name": user.display_name,
            "role": user.role.value}


def current_actor(session: Session, actor_id: int | None) -> dict | None:
    """Logged-in user card, or None."""
    from DataModels import AppUser

    if actor_id is None:
        return None
    user = session.get(AppUser, actor_id)
    if user is None:
        return None
    return {"id": user.id, "name": user.display_name,
            "role": user.role.value}
