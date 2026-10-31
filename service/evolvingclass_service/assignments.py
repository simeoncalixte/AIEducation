"""Lesson assignments to classrooms or individual students (SCRUM-125, SCRUM-18)."""

from __future__ import annotations

from sqlalchemy import select

from DataModels import (
    AppUser,
    Assignment,
    Classroom,
    Lesson,
    Membership,
    MembershipStatus,
    UserRole,
)

from .directives import require_classroom_student
from .errors import (
    FORBIDDEN,
    INVALID_SCOPE,
    NOT_FOUND,
    PublicationError,
)
from .publication import SessionFactory

_PUBLISHERS = frozenset({UserRole.teacher, UserRole.admin})


def assign_lesson(
    make_session: SessionFactory,
    lesson_id: int,
    actor_id: int,
    classroom_id: int | None = None,
    student_id: int | None = None,
) -> int:
    """Assign a lesson to exactly one classroom or student.

    Returns the assignment id, reusing the existing row when the same
    lesson is already assigned to the same target.
    """
    if (classroom_id is None) == (student_id is None):
        raise PublicationError(
            INVALID_SCOPE,
            "Assign to exactly one classroom or one student.",
        )
    with make_session() as session, session.begin():
        lesson = session.get(Lesson, lesson_id)
        if lesson is None:
            raise PublicationError(
                NOT_FOUND, f"Unknown lesson {lesson_id}.")
        actor = session.get(AppUser, actor_id)
        if actor is None:
            raise PublicationError(NOT_FOUND, f"Unknown actor {actor_id}.")
        if actor.role not in _PUBLISHERS:
            raise PublicationError(
                FORBIDDEN,
                f"Role {actor.role.value} may not assign; "
                "teacher or admin required.",
            )
        if classroom_id is not None:
            classroom = session.get(Classroom, classroom_id)
            if classroom is None:
                raise PublicationError(
                    NOT_FOUND, f"Unknown classroom {classroom_id}.")
            if classroom.school_id != lesson.school_id:
                raise PublicationError(
                    INVALID_SCOPE,
                    "A lesson can only be assigned inside its school.")
            existing = session.scalar(
                select(Assignment.id).where(
                    Assignment.lesson_id == lesson_id,
                    Assignment.classroom_id == classroom_id,
                ))
        else:
            assert student_id is not None
            require_classroom_student(session, lesson, student_id)
            existing = session.scalar(
                select(Assignment.id).where(
                    Assignment.lesson_id == lesson_id,
                    Assignment.student_id == student_id,
                ))
        if existing is not None:
            return existing
        assignment = Assignment(
            lesson_id=lesson_id,
            classroom_id=classroom_id,
            student_id=student_id,
            assigned_by_id=actor_id,
        )
        session.add(assignment)
        session.flush()
        assert assignment.id is not None
        return assignment.id


__all__ = ["assign_lesson"]
