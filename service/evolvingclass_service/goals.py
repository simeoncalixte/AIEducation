"""Deterministic goal evaluation over attempt telemetry (SCRUM-20).

A deterministic rule names the evidence it needs::

    {"verb": "goal-attempted", "object_ref": "crater",
     "require": "present"}

``require`` is ``present`` (at least one matching client event),
``absent`` (no matching event), or ``{"count_gte": N}``. Rules that do
not match this schema, and teacher-graded goals, produce no verdict —
the teacher grades those from recorded evidence. Evaluation is a pure
function of the attempt's client-origin events in sequence order, so
re-running stored events always yields the same verdicts; verdicts are
recomputed, never replayed. Each verdict payload records the consumed
sequence watermark (``evaluated_upto_sequence``) alongside the
evaluator version, so late arrivals stay excluded from verdicts
already issued (SCRUM-37).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from sqlalchemy import func, select

from DataModels import (
    AssetKind,
    Attempt,
    EventOrigin,
    ExperienceEvent,
    Goal,
    GoalEvaluation,
)

from .errors import NOT_FOUND, PublicationError
from .publication import SessionFactory

EVALUATOR_VERSION = "goals/v1"
VERDICT_VERB = "goal-verdict"


def match_rule(rule: Mapping[str, Any],
               events: Sequence[ExperienceEvent]) -> bool | None:
    """Evaluate one rule over ordered client events.

    Returns pass/fail, or None when the rule is not evaluable.
    """
    if not isinstance(rule, dict):
        return None
    verb = rule.get("verb")
    if not isinstance(verb, str) or not verb:
        return None
    want_ref = rule.get("object_ref")
    if want_ref is not None and not isinstance(want_ref, str):
        return None
    require = rule.get("require", "present")
    count = sum(
        1 for e in events
        if e.verb == verb and (want_ref is None or e.object_ref == want_ref)
    )
    if require == "present":
        return count >= 1
    if require == "absent":
        return count == 0
    if isinstance(require, dict) and isinstance(
            require.get("count_gte"), int):
        return count >= require["count_gte"]
    return None


def _challenge_goals(session, attempt: Attempt) -> list[Goal]:
    goals: list[Goal] = []
    for link in sorted(attempt.pinned_lesson_version.composition,
                       key=lambda l: l.position):
        for use in sorted(link.stage_version.asset_uses,
                          key=lambda u: u.position):
            challenge = use.asset_version
            if challenge.asset.kind is not AssetKind.challenge:
                continue
            goals.extend(sorted(challenge.goals, key=lambda gl: gl.key))
    return [g for g in goals
            if g.evaluation is GoalEvaluation.deterministic]


def evaluate_attempt(
    make_session: SessionFactory,
    attempt_id: int,
    evaluator_version: str = EVALUATOR_VERSION,
) -> list[int]:
    """Issue goal verdicts for an attempt; skips verdicts already issued.

    Returns the ids of newly created verdict events.
    """
    with make_session() as session, session.begin():
        attempt = session.get(Attempt, attempt_id)
        if attempt is None:
            raise PublicationError(
                NOT_FOUND, f"Unknown attempt {attempt_id}.")
        events = list(session.scalars(
            select(ExperienceEvent)
            .where(
                ExperienceEvent.attempt_id == attempt_id,
                ExperienceEvent.origin == EventOrigin.client,
            )
            .order_by(ExperienceEvent.sequence_no)
        ))
        issued = {
            row[0]
            for row in session.execute(
                select(ExperienceEvent.goal_id)
                .where(
                    ExperienceEvent.attempt_id == attempt_id,
                    ExperienceEvent.verb == VERDICT_VERB,
                    ExperienceEvent.evaluator_version == evaluator_version,
                )
            ).all()
        }
        watermark = max(
            (event.sequence_no for event in events), default=0)
        new_ids: list[int] = []
        for goal in _challenge_goals(session, attempt):
            if goal.id in issued:
                continue
            passed = match_rule(goal.rule or {}, events)
            if passed is None:
                continue
            sequence_no = (session.scalar(
                select(func.max(ExperienceEvent.sequence_no)).where(
                    ExperienceEvent.attempt_id == attempt_id)
            ) or 0) + 1
            verdict = ExperienceEvent(
                attempt_id=attempt_id,
                client_event_id=f"verdict-{goal.id}-{evaluator_version}",
                sequence_no=sequence_no,
                origin=EventOrigin.server,
                actor_id=attempt.student_id,
                verb=VERDICT_VERB,
                object_type="goal",
                object_ref=goal.key,
                goal_id=goal.id,
                challenge_version_id=goal.challenge_version_id,
                evaluator_version=evaluator_version,
                payload={
                    "passed": passed,
                    "goal_key": goal.key,
                    "evaluated_upto_sequence": watermark,
                    "evidence": f"rule {dict(goal.rule or {})} "
                                f"over {len(events)} client event(s)",
                },
            )
            session.add(verdict)
            session.flush()
            assert verdict.id is not None
            new_ids.append(verdict.id)
        return new_ids


__all__ = ["EVALUATOR_VERSION", "VERDICT_VERB", "evaluate_attempt",
           "match_rule"]
