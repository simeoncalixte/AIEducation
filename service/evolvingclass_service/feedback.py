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
    Goal,
    GoalEvaluation,
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
TEACHER_EVAL_VERB = "teacher-evaluation"
TEACHER_EVALUATOR_VERSION = "teacher/v1"


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


def _challenge_in_attempt_composition(
    attempt: Attempt, challenge_version_id: int
) -> bool:
    for link in attempt.pinned_lesson_version.composition:
        for use in link.stage_version.asset_uses:
            if use.asset_version_id == challenge_version_id:
                return True
    return False


def record_teacher_evaluation(
    make_session: SessionFactory,
    attempt_id: int,
    goal_id: int,
    actor_id: int,
    passed: bool,
    rationale: str = "",
) -> int:
    """Grade a teacher-evaluated goal from recorded evidence.

    Emits one server ``teacher-evaluation`` event per attempt goal;
    deterministic goals and repeat grades are rejected (re-grading
    arrives with the rubric grading view). Returns the event id.
    """
    if not isinstance(passed, bool):
        raise PublicationError(
            INVALID_FEEDBACK, "An evaluation needs a pass/fail verdict.")
    if not isinstance(goal_id, int) or isinstance(goal_id, bool):
        raise PublicationError(
            INVALID_FEEDBACK, "An evaluation needs a goal id.")
    with make_session() as session, session.begin():
        attempt = session.get(Attempt, attempt_id)
        if attempt is None:
            raise PublicationError(
                NOT_FOUND, f"Unknown attempt {attempt_id}.")
        _require_teacher_or_admin(session, actor_id)
        goal = session.get(Goal, goal_id)
        if goal is None:
            raise PublicationError(
                NOT_FOUND, f"Unknown goal {goal_id}.")
        if goal.evaluation is not GoalEvaluation.teacher:
            raise PublicationError(
                INVALID_FEEDBACK,
                "Only teacher-graded goals take a teacher evaluation.")
        if not _challenge_in_attempt_composition(
                attempt, goal.challenge_version_id):
            raise PublicationError(
                INVALID_SCOPE,
                "Evaluations must grade a challenge of the "
                "attempt's lesson.")
        graded = session.scalar(
            select(ExperienceEvent.id).where(
                ExperienceEvent.attempt_id == attempt_id,
                ExperienceEvent.goal_id == goal_id,
                ExperienceEvent.verb == TEACHER_EVAL_VERB,
            )
        )
        if graded is not None:
            raise PublicationError(
                INVALID_FEEDBACK,
                f"Goal {goal.key!r} is already evaluated.")
        event = ExperienceEvent(
            attempt_id=attempt_id,
            client_event_id=f"teacher-eval-{goal_id}",
            sequence_no=_next_sequence(session, attempt_id),
            origin=EventOrigin.server,
            actor_id=actor_id,
            verb=TEACHER_EVAL_VERB,
            object_type="goal",
            object_ref=goal.key,
            goal_id=goal.id,
            challenge_version_id=goal.challenge_version_id,
            evaluator_version=TEACHER_EVALUATOR_VERSION,
            payload={"passed": passed, "goal_key": goal.key,
                     "rationale": rationale},
        )
        session.add(event)
        session.flush()
        assert event.id is not None
        return event.id


__all__ = [
    "FLAG_VERB",
    "TEACHER_EVAL_VERB",
    "TEACHER_EVALUATOR_VERSION",
    "VERDICT_VERB",
    "flag_misconception",
    "record_teacher_evaluation",
    "record_verdict_override",
]
