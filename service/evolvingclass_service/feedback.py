"""Teacher feedback on play: verdict overrides and misconception flags.

Overrides correct deterministic verdicts with a required reason; the
history is append-only with latest-wins applied at read time. Flags
record teacher-observed misconceptions as server-origin events that
feed the evolution loop (SCRUM-19).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from DataModels import (
    AppUser,
    Attempt,
    EventOrigin,
    ExperienceEvent,
    Misconception,
    UserRole,
    VerdictOverride,
)

from .errors import (
    FORBIDDEN,
    INVALID_FEEDBACK,
    INVALID_SCOPE,
    NOT_FOUND,
    PublicationError,
)
from .publication import SessionFactory

_PUBLISHERS = frozenset({UserRole.teacher, UserRole.admin})

VERDICT_VERB = "goal-verdict"
FLAG_VERB = "misconception-flagged"


def _require_teacher_or_admin(session, actor_id: int) -> None:
    actor = session.get(AppUser, actor_id)
    if actor is None:
        raise PublicationError(NOT_FOUND, f"Unknown actor {actor_id}.")
    if actor.role not in _PUBLISHERS:
        raise PublicationError(
            FORBIDDEN,
            f"Role {actor.role.value} may not give feedback; "
            "teacher or admin required.",
        )


def _next_sequence(session, attempt_id: int) -> int:
    return (session.scalar(
        select(func.max(ExperienceEvent.sequence_no)).where(
            ExperienceEvent.attempt_id == attempt_id)
    ) or 0) + 1


def record_verdict_override(
    make_session: SessionFactory,
    verdict_event_id: int,
    actor_id: int,
    reason: str,
    corrected_passed: bool,
    corrected_score: float | None = None,
) -> int:
    """Append a correction to a goal-verdict event. Returns override id."""
    reason = reason.strip()
    if not reason:
        raise PublicationError(
            INVALID_FEEDBACK, "An override needs a reason.")
    if corrected_score is not None and not 0.0 <= corrected_score <= 1.0:
        raise PublicationError(
            INVALID_FEEDBACK, "Corrected score must fall between 0 and 1.")
    with make_session() as session, session.begin():
        event = session.get(ExperienceEvent, verdict_event_id)
        if event is None:
            raise PublicationError(
                NOT_FOUND, f"Unknown event {verdict_event_id}.")
        if event.verb != VERDICT_VERB:
            raise PublicationError(
                INVALID_FEEDBACK,
                f"Only {VERDICT_VERB} events can be overridden.")
        _require_teacher_or_admin(session, actor_id)
        override = VerdictOverride(
            verdict_event_id=verdict_event_id,
            teacher_id=actor_id,
            reason=reason,
            corrected_passed=bool(corrected_passed),
            corrected_score=corrected_score,
        )
        session.add(override)
        session.flush()
        assert override.id is not None
        return override.id


def flag_misconception(
    make_session: SessionFactory,
    attempt_id: int,
    actor_id: int,
    misconception_id: int | None = None,
    note: str = "",
) -> int:
    """Record a teacher-observed misconception as an event.

    Returns the new event id. Either a known misconception or a note
    is required.
    """
    note = note.strip()
    if misconception_id is None and not note:
        raise PublicationError(
            INVALID_FEEDBACK,
            "A flag needs a misconception, a note, or both.")
    with make_session() as session, session.begin():
        attempt = session.get(Attempt, attempt_id)
        if attempt is None:
            raise PublicationError(
                NOT_FOUND, f"Unknown attempt {attempt_id}.")
        _require_teacher_or_admin(session, actor_id)
        if misconception_id is not None:
            misconception = session.get(Misconception, misconception_id)
            if misconception is None:
                raise PublicationError(
                    NOT_FOUND, f"Unknown misconception {misconception_id}.")
            lesson_id = misconception.mental_model.lesson_version.lesson_id
            if lesson_id != attempt.assignment.lesson_id:
                raise PublicationError(
                    INVALID_SCOPE,
                    "Flags must reference a misconception of the "
                    "attempt's lesson.")
        event = ExperienceEvent(
            attempt_id=attempt_id,
            client_event_id=f"flag-{uuid.uuid4().hex[:12]}",
            sequence_no=_next_sequence(session, attempt_id),
            origin=EventOrigin.server,
            actor_id=actor_id,
            verb=FLAG_VERB,
            object_type="misconception",
            object_ref=str(misconception_id or "general"),
            payload={"note": note, "misconception_id": misconception_id},
        )
        session.add(event)
        session.flush()
        assert event.id is not None
        return event.id


__all__ = [
    "FLAG_VERB",
    "VERDICT_VERB",
    "flag_misconception",
    "record_verdict_override",
]
