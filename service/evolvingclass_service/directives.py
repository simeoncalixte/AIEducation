"""Teacher directives: steer agents class-wide or per student.

Steer directives record goal focus and constraints for a lesson without
drafting anything; briefs (briefing.py) additionally draft a lesson
proposal. Per-student directives may only target students of the
lesson classroom (SCRUM-123, SCRUM-17).
"""

from __future__ import annotations

from typing import Mapping

from sqlalchemy import select

from DataModels import (
    AppUser,
    Classroom,
    Directive,
    DirectiveKind,
    Lesson,
    Membership,
    MembershipStatus,
    UserRole,
)

from .errors import (
    FORBIDDEN,
    INVALID_DIRECTIVE,
    INVALID_SCOPE,
    NOT_FOUND,
    PublicationError,
)
from .publication import SessionFactory

_PUBLISHERS = frozenset({UserRole.teacher, UserRole.admin})


def _require_teacher_or_admin(session, actor_id: int) -> None:
    actor = session.get(AppUser, actor_id)
    if actor is None:
        raise PublicationError(NOT_FOUND, f"Unknown actor {actor_id}.")
    if actor.role not in _PUBLISHERS:
        raise PublicationError(
            FORBIDDEN,
            f"Role {actor.role.value} may not direct agents; "
            "teacher or admin required.",
        )


def _require_lesson(session, lesson_id: int) -> Lesson:
    lesson = session.get(Lesson, lesson_id)
    if lesson is None:
        raise PublicationError(NOT_FOUND, f"Unknown lesson {lesson_id}.")
    return lesson


def require_classroom_student(
    session, lesson: Lesson, student_id: int
) -> None:
    """Reject per-student targeting outside the lesson classroom."""
    student = session.get(AppUser, student_id)
    if student is None:
        raise PublicationError(NOT_FOUND, f"Unknown student {student_id}.")
    if student.role is not UserRole.student:
        raise PublicationError(
            INVALID_SCOPE, "Only students can be targeted per student.")
    scope = (Membership.classroom_id == lesson.classroom_id)
    if lesson.classroom_id is None:
        scope = (Membership.school_id == lesson.school_id) | (
            Classroom.school_id == lesson.school_id)
    local = session.scalar(
        select(Membership.id)
        .outerjoin(Classroom, Membership.classroom_id == Classroom.id)
        .where(
            Membership.user_id == student_id,
            Membership.status == MembershipStatus.active,
            scope,
        )
    )
    if local is None:
        raise PublicationError(
            INVALID_SCOPE,
            "Per-student directives must target a student "
            "of the lesson classroom.",
        )


def _clean_focus(focus: str) -> str:
    focus = focus.strip()
    if not focus:
        raise PublicationError(
            INVALID_DIRECTIVE, "A directive needs a focus.")
    return focus


def create_steer_directive(
    make_session: SessionFactory,
    lesson_id: int,
    actor_id: int,
    focus: str,
    constraints: Mapping[str, object] | None = None,
    priority: int = 1,
    student_id: int | None = None,
) -> int:
    """Record a kind=steer directive; None scope means class-wide."""
    focus = _clean_focus(focus)
    with make_session() as session, session.begin():
        lesson = _require_lesson(session, lesson_id)
        _require_teacher_or_admin(session, actor_id)
        if student_id is not None:
            require_classroom_student(session, lesson, student_id)
        directive = Directive(
            lesson_id=lesson_id,
            student_id=student_id,
            kind=DirectiveKind.steer,
            focus=focus,
            constraints=dict(constraints or {}),
            priority=priority,
            author_id=actor_id,
            active=True,
        )
        session.add(directive)
        session.flush()
        assert directive.id is not None
        return directive.id


def update_directive(
    make_session: SessionFactory,
    directive_id: int,
    actor_id: int,
    focus: str | None = None,
    constraints: Mapping[str, object] | None = None,
    priority: int | None = None,
) -> None:
    """Edit a directive's focus, constraints, or priority."""
    with make_session() as session, session.begin():
        directive = session.get(Directive, directive_id)
        if directive is None:
            raise PublicationError(
                NOT_FOUND, f"Unknown directive {directive_id}.")
        _require_teacher_or_admin(session, actor_id)
        if focus is not None:
            directive.focus = _clean_focus(focus)
        if constraints is not None:
            directive.constraints = dict(constraints)
        if priority is not None:
            directive.priority = priority


def deactivate_directive(
    make_session: SessionFactory,
    directive_id: int,
    actor_id: int,
) -> None:
    """Take a directive out of the active set (idempotent)."""
    with make_session() as session, session.begin():
        directive = session.get(Directive, directive_id)
        if directive is None:
            raise PublicationError(
                NOT_FOUND, f"Unknown directive {directive_id}.")
        _require_teacher_or_admin(session, actor_id)
        directive.active = False


__all__ = [
    "create_steer_directive",
    "deactivate_directive",
    "require_classroom_student",
    "update_directive",
]
