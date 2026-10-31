"""Student play: attempts, challenge answers, finishing, ratings, retry.

Attempts pin the served lesson version plus its stage composition, so
mid-lesson publishes never disrupt play. Answering a challenge records
client telemetry and immediately evaluates deterministic goals, so
verdicts land in the same session (SCRUM-126, SCRUM-20).
"""

from __future__ import annotations

import datetime as _dt

from sqlalchemy import func, select

from DataModels import (
    AppUser,
    AssetKind,
    Assignment,
    Attempt,
    AttemptPin,
    EventOrigin,
    ExperienceEvent,
    LessonVersionStage,
    Membership,
    MembershipStatus,
    Rating,
    UserRole,
)

from .errors import (
    FORBIDDEN,
    INVALID_PLAY,
    NOT_FOUND,
    PublicationError,
)
from .goals import evaluate_attempt
from .publication import SessionFactory, resolve_current_lesson_version

ANSWER_VERB = "goal-attempted"


def _require_student(session, student_id: int) -> AppUser:
    student = session.get(AppUser, student_id)
    if student is None:
        raise PublicationError(NOT_FOUND, f"Unknown student {student_id}.")
    if student.role is not UserRole.student:
        raise PublicationError(
            FORBIDDEN, "Only students can play assigned lessons.")
    return student


def _require_owner(session, attempt_id: int, student_id: int) -> Attempt:
    attempt = session.get(Attempt, attempt_id)
    if attempt is None:
        raise PublicationError(NOT_FOUND, f"Unknown attempt {attempt_id}.")
    if attempt.student_id != student_id:
        raise PublicationError(
            FORBIDDEN, "An attempt belongs to its student.")
    return attempt


def _in_assignment_scope(session, assignment: Assignment,
                         student_id: int) -> bool:
    if assignment.student_id is not None:
        return assignment.student_id == student_id
    return session.scalar(
        select(Membership.id).where(
            Membership.user_id == student_id,
            Membership.classroom_id == assignment.classroom_id,
            Membership.status == MembershipStatus.active,
        )) is not None


def _pin_stages(session, attempt_id: int, lesson_version_id: int) -> None:
    links = list(session.scalars(
        select(LessonVersionStage).where(
            LessonVersionStage.lesson_version_id == lesson_version_id)
    ))
    for link in links:
        session.add(AttemptPin(attempt_id=attempt_id,
                               stage_version_id=link.stage_version_id))


def start_attempt(
    make_session: SessionFactory,
    assignment_id: int,
    student_id: int,
) -> int:
    """Open (or resume) an attempt pinned to the served lesson version."""
    with make_session() as session, session.begin():
        assignment = session.get(Assignment, assignment_id)
        if assignment is None:
            raise PublicationError(
                NOT_FOUND, f"Unknown assignment {assignment_id}.")
        _require_student(session, student_id)
        if not _in_assignment_scope(session, assignment, student_id):
            raise PublicationError(
                FORBIDDEN, "This assignment is not yours.")
        version = resolve_current_lesson_version(
            session, assignment.lesson_id, student_id)
        if version is None:
            raise PublicationError(
                INVALID_PLAY, "This lesson has no published version yet.")
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
        if open_attempt is not None:
            return open_attempt.id
        attempt = Attempt(
            assignment_id=assignment_id,
            student_id=student_id,
            pinned_lesson_version_id=version.id,
        )
        session.add(attempt)
        session.flush()
        assert attempt.id is not None
        _pin_stages(session, attempt.id, version.id)
        return attempt.id


def answer_challenge(
    make_session: SessionFactory,
    attempt_id: int,
    student_id: int,
    challenge_version_id: int,
    goal_keys: list[str],
    note: str = "",
) -> list[int]:
    """Record telemetry for a challenge and evaluate its goals.

    Returns the ids of newly issued verdict events.
    """
    with make_session() as session, session.begin():
        attempt = _require_owner(session, attempt_id, student_id)
        if attempt.finished_at is not None:
            raise PublicationError(
                INVALID_PLAY, "This attempt is already finished.")
        pinned_stage_ids = {
            pin.stage_version_id for pin in attempt.pins}
        challenge = None
        for link in attempt.pinned_lesson_version.composition:
            if link.stage_version_id not in pinned_stage_ids:
                continue
            for use in link.stage_version.asset_uses:
                candidate = use.asset_version
                if (candidate.id == challenge_version_id
                        and candidate.asset.kind is AssetKind.challenge):
                    challenge = candidate
        if challenge is None:
            raise PublicationError(
                INVALID_PLAY, "This challenge is not in the attempt.")
        known = {goal.key for goal in challenge.goals}
        for key in goal_keys:
            if key not in known:
                raise PublicationError(
                    INVALID_PLAY, f"Unknown goal {key!r}.")
        for key in goal_keys:
            client_event_id = f"ch{challenge_version_id}-{key}"
            exists = session.scalar(
                select(ExperienceEvent.id).where(
                    ExperienceEvent.attempt_id == attempt_id,
                    ExperienceEvent.client_event_id == client_event_id,
                ))
            if exists is not None:
                continue
            sequence_no = (session.scalar(
                select(func.max(ExperienceEvent.sequence_no)).where(
                    ExperienceEvent.attempt_id == attempt_id)
            ) or 0) + 1
            goal_id = next(
                goal.id for goal in challenge.goals if goal.key == key)
            session.add(ExperienceEvent(
                attempt_id=attempt_id,
                client_event_id=client_event_id,
                sequence_no=sequence_no,
                origin=EventOrigin.client,
                actor_id=student_id,
                verb=ANSWER_VERB,
                object_type="goal",
                object_ref=key,
                goal_id=goal_id,
                challenge_version_id=challenge_version_id,
                payload={"note": note.strip()},
            ))
            session.flush()
    return evaluate_attempt(make_session, attempt_id)


def finish_attempt(
    make_session: SessionFactory,
    attempt_id: int,
    student_id: int,
) -> None:
    """Close an attempt so its verdicts stand as the result."""
    with make_session() as session, session.begin():
        attempt = _require_owner(session, attempt_id, student_id)
        if attempt.finished_at is not None:
            raise PublicationError(
                INVALID_PLAY, "This attempt is already finished.")
        attempt.finished_at = _dt.datetime.now(_dt.timezone.utc)


def rate_lesson(
    make_session: SessionFactory,
    attempt_id: int,
    student_id: int,
    score: int,
) -> int:
    """Record a 1–5 enjoyment rating for the pinned lesson version."""
    if score not in (1, 2, 3, 4, 5):
        raise PublicationError(
            INVALID_PLAY, "A rating is a whole number from 1 to 5.")
    with make_session() as session, session.begin():
        attempt = _require_owner(session, attempt_id, student_id)
        rating = Rating(
            lesson_version_id=attempt.pinned_lesson_version_id,
            author_id=student_id,
            score=score,
        )
        session.add(rating)
        session.flush()
        assert rating.id is not None
        return rating.id


def retry_attempt(
    make_session: SessionFactory,
    attempt_id: int,
    student_id: int,
) -> int:
    """Open a new attempt against the same pinned version."""
    with make_session() as session, session.begin():
        attempt = _require_owner(session, attempt_id, student_id)
        retry = Attempt(
            assignment_id=attempt.assignment_id,
            student_id=student_id,
            pinned_lesson_version_id=attempt.pinned_lesson_version_id,
            retry_of_id=attempt_id,
        )
        session.add(retry)
        session.flush()
        assert retry.id is not None
        for pin in attempt.pins:
            session.add(AttemptPin(
                attempt_id=retry.id,
                stage_version_id=pin.stage_version_id,
            ))
        return retry.id


__all__ = [
    "ANSWER_VERB",
    "answer_challenge",
    "finish_attempt",
    "rate_lesson",
    "retry_attempt",
    "start_attempt",
]
