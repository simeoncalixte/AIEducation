"""Tests for deterministic goal evaluation (SCRUM-20)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "database"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from DataModels import (  # noqa: E402
    AppUser,
    Asset,
    AssetKind,
    AssetUse,
    AssetVersion,
    Assignment,
    Attempt,
    Base,
    Classroom,
    EventOrigin,
    ExperienceEvent,
    Goal,
    GoalEvaluation,
    Lesson,
    LessonVersion,
    LessonVersionStage,
    Membership,
    MembershipStatus,
    School,
    Stage,
    StageVersion,
    UserRole,
    VersionStatus,
)
from evolvingclass_service import PublicationError  # noqa: E402
from evolvingclass_service.goals import (  # noqa: E402
    evaluate_attempt,
    match_rule,
)


class FakeEvent:
    def __init__(self, verb, object_ref="x"):
        self.verb = verb
        self.object_ref = object_ref


class MatchRuleTestCase(unittest.TestCase):
    def test_present_absent_and_count(self):
        events = [FakeEvent("a", "x"), FakeEvent("a", "x"),
                  FakeEvent("b", "y")]
        self.assertTrue(
            match_rule({"verb": "a", "require": "present"}, events))
        self.assertFalse(
            match_rule({"verb": "z", "require": "present"}, events))
        self.assertTrue(
            match_rule({"verb": "z", "require": "absent"}, events))
        self.assertFalse(
            match_rule({"verb": "a", "require": "absent"}, events))
        self.assertTrue(
            match_rule({"verb": "a", "require": {"count_gte": 2}},
                       events))
        self.assertFalse(
            match_rule({"verb": "a", "require": {"count_gte": 3}},
                       events))

    def test_object_ref_scoping(self):
        events = [FakeEvent("a", "x")]
        self.assertTrue(
            match_rule({"verb": "a", "object_ref": "x"}, events))
        self.assertFalse(
            match_rule({"verb": "a", "object_ref": "y"}, events))

    def test_unevaluable_rules_return_none(self):
        events = [FakeEvent("a", "x")]
        self.assertIsNone(match_rule({}, events))
        self.assertIsNone(match_rule({"verb": ""}, events))
        self.assertIsNone(match_rule({"verb": "a", "require": "maybe"},
                                     events))
        self.assertIsNone(match_rule({"verb": "a", "object_ref": 3},
                                     events))
        self.assertIsNone(match_rule("nope", events))


class EvaluateAttemptTestCase(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.make_session = sessionmaker(bind=engine)
        with self.make_session() as session, session.begin():
            school = School(name="Pilot School")
            session.add(school)
            session.flush()
            room = Classroom(school_id=school.id, name="Room 1")
            session.add(room)
            session.flush()
            teacher = AppUser(role=UserRole.teacher, display_name="T",
                              login_ref="teacher-1")
            student = AppUser(role=UserRole.student, display_name="S",
                              login_ref="student-1")
            session.add_all([teacher, student])
            session.flush()
            lesson = Lesson(school_id=school.id, classroom_id=room.id,
                            subject="science", title="L")
            session.add(lesson)
            session.flush()
            lesson_v = LessonVersion(
                lesson_id=lesson.id, version_no=1,
                status=VersionStatus.published, rationale="r",
                objective_refs=[])
            session.add(lesson_v)
            session.flush()
            stage = Stage(lesson_id=lesson.id, position=1, title="S")
            session.add(stage)
            session.flush()
            stage_v = StageVersion(stage_id=stage.id, version_no=1,
                                   status=VersionStatus.published,
                                   rationale="r")
            session.add(stage_v)
            session.flush()
            session.add(LessonVersionStage(
                lesson_version_id=lesson_v.id,
                stage_version_id=stage_v.id, position=1))
            asset = Asset(kind=AssetKind.challenge, title="C",
                          created_by_id=teacher.id, school_id=school.id)
            session.add(asset)
            session.flush()
            challenge = AssetVersion(
                asset_id=asset.id, version_no=1,
                status=VersionStatus.published, rationale="r",
                objective_refs=[], content_ref="c", param_schema={})
            session.add(challenge)
            session.flush()
            session.add(AssetUse(asset_version_id=challenge.id,
                                 stage_version_id=stage_v.id, position=1,
                                 role="challenge", param_overrides={}))
            session.add_all([
                Goal(challenge_version_id=challenge.id, key="crater",
                     rule={"verb": "goal-attempted", "object_ref": "crater",
                           "require": "present"},
                     evaluation=GoalEvaluation.deterministic,
                     template_ref="t"),
                Goal(challenge_version_id=challenge.id, key="quiet",
                     rule={"verb": "shouted", "require": "absent"},
                     evaluation=GoalEvaluation.deterministic,
                     template_ref="t"),
                Goal(challenge_version_id=challenge.id, key="essay",
                     rule={}, evaluation=GoalEvaluation.teacher,
                     rubric={"prompt": "Explain."}, template_ref="t"),
            ])
            session.flush()
            assignment = Assignment(
                lesson_id=lesson.id, classroom_id=room.id,
                assigned_by_id=teacher.id)
            session.add(assignment)
            session.flush()
            attempt = Attempt(assignment_id=assignment.id,
                              student_id=student.id,
                              pinned_lesson_version_id=lesson_v.id)
            session.add(attempt)
            session.flush()
            self.attempt_id = attempt.id
            self.student_id = student.id
            self.seq = 0

    def _emit(self, verb, ref="crater", origin=EventOrigin.client):
        with self.make_session() as session, session.begin():
            self.seq += 1
            session.add(ExperienceEvent(
                attempt_id=self.attempt_id,
                client_event_id=f"e{self.seq}-{verb}-{ref}",
                sequence_no=self.seq, origin=origin,
                actor_id=self.student_id, verb=verb,
                object_type="goal", object_ref=ref, payload={}))

    def _verdicts(self):
        with self.make_session() as session:
            rows = list(session.scalars(
                select(ExperienceEvent)
                .where(ExperienceEvent.attempt_id == self.attempt_id,
                       ExperienceEvent.verb == "goal-verdict")
                .order_by(ExperienceEvent.id)))
            return [(r.object_ref, r.payload["passed"],
                     r.evaluator_version, r.origin, r.actor_id)
                    for r in rows]

    def test_verdicts_follow_telemetry(self):
        self._emit("goal-attempted", "crater")
        new_ids = evaluate_attempt(self.make_session, self.attempt_id)
        self.assertEqual(len(new_ids), 2)
        verdicts = dict((ref, passed) for ref, passed, _, _, _ in
                        self._verdicts())
        self.assertEqual(verdicts, {"crater": True, "quiet": True})

    def test_absent_rule_fails_on_matching_event(self):
        self._emit("shouted", "loud")
        evaluate_attempt(self.make_session, self.attempt_id)
        verdicts = dict((ref, passed) for ref, passed, _, _, _ in
                        self._verdicts())
        self.assertEqual(verdicts, {"crater": False, "quiet": False})

    def test_teacher_goals_produce_no_verdict(self):
        self._emit("goal-attempted", "crater")
        evaluate_attempt(self.make_session, self.attempt_id)
        refs = [ref for ref, _, _, _, _ in self._verdicts()]
        self.assertNotIn("essay", refs)

    def test_verdict_shape(self):
        self._emit("goal-attempted", "crater")
        evaluate_attempt(self.make_session, self.attempt_id)
        with self.make_session() as session:
            row = session.scalar(
                select(ExperienceEvent)
                .where(ExperienceEvent.attempt_id == self.attempt_id,
                       ExperienceEvent.verb == "goal-verdict",
                       ExperienceEvent.object_ref == "crater"))
            self.assertEqual(row.origin, EventOrigin.server)
            self.assertEqual(row.actor_id, self.student_id)
            self.assertEqual(row.evaluator_version, "goals/v1")
            self.assertIsNotNone(row.goal_id)
            self.assertIsNotNone(row.challenge_version_id)
            self.assertEqual(row.payload["goal_key"], "crater")
            self.assertEqual(row.sequence_no, 2)

    def test_rerun_issues_nothing_new(self):
        self._emit("goal-attempted", "crater")
        first = evaluate_attempt(self.make_session, self.attempt_id)
        second = evaluate_attempt(self.make_session, self.attempt_id)
        self.assertEqual(len(first), 2)
        self.assertEqual(second, [])
        self.assertEqual(len(self._verdicts()), 2)

    def test_replay_recomputes_identical_verdicts(self):
        self._emit("goal-attempted", "crater")
        evaluate_attempt(self.make_session, self.attempt_id)
        before = self._verdicts()
        with self.make_session() as session, session.begin():
            for row in session.scalars(
                    select(ExperienceEvent).where(
                        ExperienceEvent.attempt_id == self.attempt_id,
                        ExperienceEvent.verb == "goal-verdict")):
                session.delete(row)
        evaluate_attempt(self.make_session, self.attempt_id)
        after = self._verdicts()
        self.assertEqual(
            [(ref, passed) for ref, passed, _, _, _ in before],
            [(ref, passed) for ref, passed, _, _, _ in after])

    def test_unknown_attempt(self):
        with self.assertRaises(PublicationError) as ctx:
            evaluate_attempt(self.make_session, 9999)
        self.assertEqual(ctx.exception.code, "not_found")

    def test_verdict_records_consumed_watermark(self):
        self._emit("goal-attempted", "crater")
        self._emit("viewed", "vent")
        evaluate_attempt(self.make_session, self.attempt_id)
        with self.make_session() as session:
            rows = list(session.scalars(
                select(ExperienceEvent).where(
                    ExperienceEvent.attempt_id == self.attempt_id,
                    ExperienceEvent.verb == "goal-verdict")))
            self.assertEqual(len(rows), 2)
            for row in rows:
                self.assertEqual(
                    row.payload["evaluated_upto_sequence"], 2)
                self.assertEqual(row.evaluator_version, "goals/v1")

    def test_late_events_do_not_alter_issued_verdicts(self):
        self._emit("goal-attempted", "crater")
        evaluate_attempt(self.make_session, self.attempt_id)
        before = self._verdicts()
        # A late arrival that would flip the "quiet" absent-rule.
        with self.make_session() as session:
            self.seq = session.scalar(
                select(func.max(ExperienceEvent.sequence_no)).where(
                    ExperienceEvent.attempt_id == self.attempt_id))
        self._emit("shouted", "loud")
        self.assertEqual(
            evaluate_attempt(self.make_session, self.attempt_id), [])
        self.assertEqual(self._verdicts(), before)
        with self.make_session() as session:
            rows = list(session.scalars(
                select(ExperienceEvent).where(
                    ExperienceEvent.attempt_id == self.attempt_id,
                    ExperienceEvent.verb == "goal-verdict")))
            for row in rows:
                self.assertEqual(
                    row.payload["evaluated_upto_sequence"], 1)

    def test_replay_reproduces_watermarks(self):
        self._emit("goal-attempted", "crater")
        self._emit("viewed", "vent")
        evaluate_attempt(self.make_session, self.attempt_id)
        with self.make_session() as session:
            before = sorted(
                (r.object_ref, r.payload["evaluated_upto_sequence"])
                for r in session.scalars(
                    select(ExperienceEvent).where(
                        ExperienceEvent.attempt_id == self.attempt_id,
                        ExperienceEvent.verb == "goal-verdict")))
        with self.make_session() as session, session.begin():
            for row in session.scalars(
                    select(ExperienceEvent).where(
                        ExperienceEvent.attempt_id == self.attempt_id,
                        ExperienceEvent.verb == "goal-verdict")):
                session.delete(row)
        evaluate_attempt(self.make_session, self.attempt_id)
        with self.make_session() as session:
            after = sorted(
                (r.object_ref, r.payload["evaluated_upto_sequence"])
                for r in session.scalars(
                    select(ExperienceEvent).where(
                        ExperienceEvent.attempt_id == self.attempt_id,
                        ExperienceEvent.verb == "goal-verdict")))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
