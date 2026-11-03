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
    ImpactRollup,
    MasteryEvidence,
    MasteryRecord,
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
TEACHER_FORMULA_VERSION = "teacher/v1"


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


def _apply_teacher_mastery(session, attempt: Attempt, goal: Goal,
                           event: ExperienceEvent, passed: bool) -> None:
    """Point the student's mastery at the latest teacher outcome.

    One record per mental model the goal verifies; each grade appends
    its evidence link, so re-grades keep the full history while the
    score follows the latest grade.
    """
    for model in sorted(goal.mental_models, key=lambda m: m.id):
        record = session.scalar(
            select(MasteryRecord).where(
                MasteryRecord.student_id == attempt.student_id,
                MasteryRecord.mental_model_id == model.id,
            )
        )
        if record is None:
            record = MasteryRecord(
                student_id=attempt.student_id,
                mental_model_id=model.id,
                score=float(passed),
                confidence=0.5,
            )
            session.add(record)
            session.flush()
        else:
            record.score = float(passed)
            seen = session.scalar(
                select(func.count()).where(
                    MasteryEvidence.mastery_record_id == record.id,
                )
            ) or 0
            record.confidence = 1.0 - 0.5 / (seen + 1)
        session.add(MasteryEvidence(
            mastery_record_id=record.id,
            experience_event_id=event.id,
            source=TEACHER_EVAL_VERB,
            weight=1.0,
        ))


def _refresh_teacher_impact(session, challenge_version_id: int) -> None:
    """Snapshot the challenge's teacher-grade pass rate (SCRUM-38).

    Mastery is the mean over latest teacher outcomes per attempt goal;
    completion and enjoyment stay 0 until the deterministic verdict and
    rating aggregations land, and the formula version marks the row as
    teacher-signal-only.
    """
    rows = session.execute(
        select(ExperienceEvent.attempt_id, ExperienceEvent.goal_id,
               ExperienceEvent.payload)
        .join(Goal, ExperienceEvent.goal_id == Goal.id)
        .where(
            Goal.challenge_version_id == challenge_version_id,
            Goal.evaluation == GoalEvaluation.teacher,
            ExperienceEvent.verb == TEACHER_EVAL_VERB,
        )
        .order_by(ExperienceEvent.id)
    ).all()
    latest: dict[tuple[int, int], bool] = {}
    for attempt_id, goal_id, payload in rows:
        latest[(attempt_id, goal_id)] = bool((payload or {}).get("passed"))
    if not latest:
        return
    mastery = (
        sum(1.0 if passed else 0.0 for passed in latest.values())
        / len(latest)
    )
    session.add(ImpactRollup(
        asset_version_id=challenge_version_id,
        window="all",
        mastery=mastery,
        completion=0.0,
        enjoyment=0.0,
        sample_size=len(latest),
        formula_version=TEACHER_FORMULA_VERSION,
    ))


def record_teacher_evaluation(
    make_session: SessionFactory,
    attempt_id: int,
    goal_id: int,
    actor_id: int,
    passed: bool,
    rationale: str = "",
) -> int:
    """Grade a teacher-evaluated goal from recorded evidence.

    Each grade appends a server ``teacher-evaluation`` event; repeat
    grades are allowed with latest-wins applied at read time (the same
    history policy as verdict overrides). The grade upserts the
    student's mastery for the goal's mental models and snapshots the
    challenge's teacher-grade impact. Returns the event id.
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
        event = ExperienceEvent(
            attempt_id=attempt_id,
            client_event_id=f"teacher-eval-{goal_id}-{uuid.uuid4().hex[:12]}",
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
        _apply_teacher_mastery(session, attempt, goal, event, passed)
        _refresh_teacher_impact(session, goal.challenge_version_id)
        return event.id


__all__ = [
    "FLAG_VERB",
    "TEACHER_EVAL_VERB",
    "TEACHER_EVALUATOR_VERSION",
    "TEACHER_FORMULA_VERSION",
    "VERDICT_VERB",
    "flag_misconception",
    "record_teacher_evaluation",
    "record_verdict_override",
]
