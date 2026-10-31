"""Teacher briefing: persist a brief directive and draft the lesson.

One transaction per brief (SCRUM-15):

1. The actor is a teacher or admin (publish-time membership checks in
   publication.py still gate anything going live).
2. A ``directive`` of kind ``brief`` records the teacher's focus and
   constraints for the lesson.
3. A draft ``lesson_version`` proposes the lesson: rationale composed
   from the brief, the briefed objectives, a snapshot of the lesson's
   active directives, and the briefed mental models.

The draft is an ordinary proposal: it appears in the lesson review
queue with its rationale and directive snapshot for approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from sqlalchemy import func, select

from DataModels import (
    AppUser,
    Directive,
    DirectiveKind,
    GenerationRun,
    GenerationStatus,
    Lesson,
    LessonVersion,
    MentalModel,
    UserRole,
    VersionStatus,
)

from .directives import require_classroom_student
from .errors import (
    FORBIDDEN,
    INVALID_BRIEF,
    NOT_FOUND,
    PublicationError,
)
from .publication import SessionFactory

_PUBLISHERS = frozenset({UserRole.teacher, UserRole.admin})


@dataclass(frozen=True)
class BriefResult:
    """Outcome of a successful brief submission."""

    directive_id: int
    lesson_version_id: int
    version_no: int
    run_id: int


def _require_teacher_or_admin(session, actor_id: int) -> None:
    actor = session.get(AppUser, actor_id)
    if actor is None:
        raise PublicationError(NOT_FOUND, f"Unknown actor {actor_id}.")
    if actor.role not in _PUBLISHERS:
        raise PublicationError(
            FORBIDDEN,
            f"Role {actor.role.value} may not brief; "
            "teacher or admin required.",
        )


def _clean(lines: Sequence[str]) -> list[str]:
    return [line.strip() for line in lines if line.strip()]


def _rationale(focus: str, objectives: list[str],
               models: list[str]) -> str:
    parts = [f"Draft from brief: {focus}"]
    if objectives:
        parts.append(f"Objectives: {', '.join(objectives)}.")
    if models:
        parts.append(f"Mental models: {len(models)} defined.")
    return " ".join(parts)


def submit_brief(
    make_session: SessionFactory,
    lesson_id: int,
    actor_id: int,
    objectives: Sequence[str] = (),
    mental_models: Sequence[str] = (),
    focus: str = "",
    constraints: Mapping[str, object] | None = None,
    priority: int = 1,
    student_id: int | None = None,
) -> BriefResult:
    """Persist a kind=brief directive and draft a lesson proposal.

    A student scope drafts a personal variant for that classroom
    student; None drafts the class default. Returns the new
    directive, draft version, and generation run ids.
    """
    focus = focus.strip()
    if not focus:
        raise PublicationError(
            INVALID_BRIEF, "A brief needs a focus for agents to draft from."
        )
    objectives = _clean(objectives)
    models = _clean(mental_models)
    with make_session() as session, session.begin():
        lesson = session.get(Lesson, lesson_id)
        if lesson is None:
            raise PublicationError(
                NOT_FOUND, f"Unknown lesson {lesson_id}.")
        _require_teacher_or_admin(session, actor_id)
        if student_id is not None:
            require_classroom_student(session, lesson, student_id)
        directive = Directive(
            lesson_id=lesson_id,
            student_id=student_id,
            kind=DirectiveKind.brief,
            focus=focus,
            constraints=dict(constraints or {}),
            priority=priority,
            author_id=actor_id,
            active=True,
        )
        session.add(directive)
        session.flush()
        # One numbering sequence per lesson across scopes: the table
        # uniques (lesson_id, version_no), so a personal variant takes
        # the next lesson number, not a per-scope one.
        version_no = (session.scalar(
            select(func.max(LessonVersion.version_no)).where(
                LessonVersion.lesson_id == lesson_id,
            )
        ) or 0) + 1
        active = list(session.scalars(
            select(Directive)
            .where(Directive.lesson_id == lesson_id,
                   Directive.active.is_(True))
            .order_by(Directive.id)
        ))
        snapshot = {
            "brief": focus,
            "directives": [
                {
                    "id": d.id,
                    "kind": d.kind.value,
                    "focus": d.focus,
                    "constraints": dict(d.constraints or {}),
                    "priority": d.priority,
                }
                for d in active
            ],
        }
        run = GenerationRun(
            agent_ref="brief-composer",
            model_ref="template-1",
            prompt_ref="brief-composer/v1",
            params={"lesson_id": lesson_id,
                    "directive_id": directive.id,
                    "objectives": objectives},
            status=GenerationStatus.completed,
            attempts=1,
            policy_version="policy/v1",
        )
        session.add(run)
        session.flush()
        draft = LessonVersion(
            lesson_id=lesson_id,
            version_no=version_no,
            status=VersionStatus.draft,
            rationale=_rationale(focus, objectives, models),
            objective_refs=objectives,
            student_scope_id=student_id,
            generation_run_id=run.id,
            directive_snapshot=snapshot,
        )
        session.add(draft)
        session.flush()
        for position, statement in enumerate(models, start=1):
            session.add(MentalModel(
                lesson_version_id=draft.id,
                statement=statement,
                position=position,
            ))
        session.flush()
        return BriefResult(directive.id, draft.id, version_no, run.id)


__all__ = ["BriefResult", "submit_brief"]
