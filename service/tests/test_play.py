"""Tests for student play: attempts, answers, ratings, retry (SCRUM-126, SCRUM-20)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "database"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, select  # noqa: E402
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
    AttemptPin,
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
    Rating,
    School,
    Stage,
    StageVersion,
    UserRole,
    VersionStatus,
)
from evolvingclass_service import (  # noqa: E402
    PublicationError,
    answer_challenge,
    finish_attempt,
    rate_lesson,
    record_client_event,
    retry_attempt,
    start_attempt,
)


class PlayTestCase(unittest.TestCase):
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
            other = AppUser(role=UserRole.student, display_name="O",
                            login_ref="student-2")
            session.add_all([teacher, student, other])
            session.flush()
            session.add_all([
                Membership(user_id=teacher.id, classroom_id=room.id,
                           status=MembershipStatus.active),
                Membership(user_id=student.id, classroom_id=room.id,
                           status=MembershipStatus.active),
                Membership(user_id=other.id, classroom_id=room.id,
                           status=MembershipStatus.active),
            ])
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
            session.add(Goal(
                challenge_version_id=challenge.id, key="crater",
                rule={"verb": "goal-attempted", "object_ref": "crater",
                      "require": "present"},
                evaluation=GoalEvaluation.deterministic, template_ref="t"))
            session.flush()
            assignment = Assignment(
                lesson_id=lesson.id, classroom_id=room.id,
                assigned_by_id=teacher.id)
            session.add(assignment)
            session.flush()
            self.assignment_id = assignment.id
            self.lesson_version_id = lesson_v.id
            self.stage_version_id = stage_v.id
            self.challenge_id = challenge.id
            self.teacher_id = teacher.id
            self.student_id = student.id
            self.other_id = other.id

    def test_start_pins_version_and_stages(self):
        aid = start_attempt(
            self.make_session, self.assignment_id, self.student_id)
        with self.make_session() as session:
            attempt = session.get(Attempt, aid)
            self.assertEqual(attempt.pinned_lesson_version_id,
                             self.lesson_version_id)
            self.assertIsNone(attempt.finished_at)
            self.assertIsNone(attempt.retry_of_id)
            pins = list(session.scalars(
                select(AttemptPin.stage_version_id).where(
                    AttemptPin.attempt_id == aid)))
            self.assertEqual(pins, [self.stage_version_id])

    def test_start_resumes_open_attempt(self):
        first = start_attempt(
            self.make_session, self.assignment_id, self.student_id)
        second = start_attempt(
            self.make_session, self.assignment_id, self.student_id)
        self.assertEqual(first, second)

    def test_start_rejections(self):
        with self.assertRaises(PublicationError) as ctx:
            start_attempt(self.make_session, 9999, self.student_id)
        self.assertEqual(ctx.exception.code, "not_found")
        with self.assertRaises(PublicationError) as ctx:
            start_attempt(
                self.make_session, self.assignment_id, self.teacher_id)
        self.assertEqual(ctx.exception.code, "forbidden")

    def test_answer_records_events_and_verdicts(self):
        aid = start_attempt(
            self.make_session, self.assignment_id, self.student_id)
        verdict_ids = answer_challenge(
            self.make_session, aid, self.student_id, self.challenge_id,
            ["crater"], note="labeled it")
        self.assertEqual(len(verdict_ids), 1)
        with self.make_session() as session:
            telemetry = list(session.scalars(
                select(ExperienceEvent).where(
                    ExperienceEvent.attempt_id == aid,
                    ExperienceEvent.verb == "goal-attempted")))
            self.assertEqual(len(telemetry), 1)
            self.assertEqual(telemetry[0].object_ref, "crater")
            self.assertEqual(telemetry[0].payload, {"note": "labeled it"})
            verdict = session.get(ExperienceEvent, verdict_ids[0])
            self.assertEqual(verdict.verb, "goal-verdict")
            self.assertTrue(verdict.payload["passed"])

    def test_answer_is_idempotent_per_goal(self):
        aid = start_attempt(
            self.make_session, self.assignment_id, self.student_id)
        answer_challenge(
            self.make_session, aid, self.student_id, self.challenge_id,
            ["crater"])
        answer_challenge(
            self.make_session, aid, self.student_id, self.challenge_id,
            ["crater"])
        with self.make_session() as session:
            count = session.query(ExperienceEvent).filter_by(
                attempt_id=aid, verb="goal-attempted").count()
            self.assertEqual(count, 1)
            verdicts = session.query(ExperienceEvent).filter_by(
                attempt_id=aid, verb="goal-verdict").count()
            self.assertEqual(verdicts, 1)

    def test_answer_rejections(self):
        aid = start_attempt(
            self.make_session, self.assignment_id, self.student_id)
        with self.assertRaises(PublicationError) as ctx:
            answer_challenge(
                self.make_session, aid, self.other_id, self.challenge_id,
                ["crater"])
        self.assertEqual(ctx.exception.code, "forbidden")
        with self.assertRaises(PublicationError) as ctx:
            answer_challenge(
                self.make_session, aid, self.student_id, 9999, ["crater"])
        self.assertEqual(ctx.exception.code, "invalid_play")
        with self.assertRaises(PublicationError) as ctx:
            answer_challenge(
                self.make_session, aid, self.student_id, self.challenge_id,
                ["nope"])
        self.assertEqual(ctx.exception.code, "invalid_play")
        finish_attempt(self.make_session, aid, self.student_id)
        with self.assertRaises(PublicationError) as ctx:
            answer_challenge(
                self.make_session, aid, self.student_id, self.challenge_id,
                ["crater"])
        self.assertEqual(ctx.exception.code, "invalid_play")

    def test_finish_and_rate(self):
        aid = start_attempt(
            self.make_session, self.assignment_id, self.student_id)
        finish_attempt(self.make_session, aid, self.student_id)
        with self.make_session() as session:
            self.assertIsNotNone(session.get(Attempt, aid).finished_at)
        with self.assertRaises(PublicationError) as ctx:
            finish_attempt(self.make_session, aid, self.student_id)
        self.assertEqual(ctx.exception.code, "invalid_play")
        rid = rate_lesson(self.make_session, aid, self.student_id, 4)
        with self.make_session() as session:
            rating = session.get(Rating, rid)
            self.assertEqual(rating.score, 4)
            self.assertEqual(rating.lesson_version_id,
                             self.lesson_version_id)
        with self.assertRaises(PublicationError) as ctx:
            rate_lesson(self.make_session, aid, self.student_id, 6)
        self.assertEqual(ctx.exception.code, "invalid_play")

    def test_client_event_intake_is_idempotent(self):
        aid = start_attempt(
            self.make_session, self.assignment_id, self.student_id)
        first_id, first_dup = record_client_event(
            self.make_session, aid, self.student_id, "evt-1", "viewed",
            object_type="stage", object_ref="eruption",
            payload={"t": 12})
        self.assertFalse(first_dup)
        second_id, second_dup = record_client_event(
            self.make_session, aid, self.student_id, "evt-1", "viewed",
            payload={"t": 999})
        self.assertTrue(second_dup)
        self.assertEqual(second_id, first_id)
        with self.make_session() as session:
            rows = list(session.scalars(
                select(ExperienceEvent).where(
                    ExperienceEvent.attempt_id == aid)))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].payload, {"t": 12})
            self.assertEqual(rows[0].origin, EventOrigin.client)
            self.assertEqual(rows[0].sequence_no, 1)

    def test_client_event_sequences_unique_per_attempt(self):
        aid = start_attempt(
            self.make_session, self.assignment_id, self.student_id)
        for index in range(3):
            record_client_event(
                self.make_session, aid, self.student_id,
                f"evt-{index}", "viewed")
        with self.make_session() as session:
            seqs = list(session.scalars(
                select(ExperienceEvent.sequence_no).where(
                    ExperienceEvent.attempt_id == aid
                ).order_by(ExperienceEvent.sequence_no)))
            self.assertEqual(seqs, [1, 2, 3])

    def test_client_event_rejects_server_only_verbs(self):
        aid = start_attempt(
            self.make_session, self.assignment_id, self.student_id)
        for verb in ("goal-verdict", "teacher-evaluation",
                     "launch-decision"):
            with self.assertRaises(PublicationError) as ctx:
                record_client_event(
                    self.make_session, aid, self.student_id,
                    f"evt-{verb}", verb)
            self.assertEqual(ctx.exception.code, "invalid_play", verb)
        with self.make_session() as session:
            count = session.query(ExperienceEvent).filter_by(
                attempt_id=aid).count()
            self.assertEqual(count, 0)

    def test_client_event_rejections(self):
        aid = start_attempt(
            self.make_session, self.assignment_id, self.student_id)
        with self.assertRaises(PublicationError) as ctx:
            record_client_event(
                self.make_session, aid, self.student_id, "  ", "viewed")
        self.assertEqual(ctx.exception.code, "invalid_play")
        with self.assertRaises(PublicationError) as ctx:
            record_client_event(
                self.make_session, aid, self.student_id, "evt-x", "  ")
        self.assertEqual(ctx.exception.code, "invalid_play")
        with self.assertRaises(PublicationError) as ctx:
            record_client_event(
                self.make_session, aid, self.other_id, "evt-x", "viewed")
        self.assertEqual(ctx.exception.code, "forbidden")
        with self.assertRaises(PublicationError) as ctx:
            record_client_event(
                self.make_session, 9999, self.student_id, "evt-x",
                "viewed")
        self.assertEqual(ctx.exception.code, "not_found")

    def test_retry_opens_new_attempt_on_same_pins(self):
        aid = start_attempt(
            self.make_session, self.assignment_id, self.student_id)
        finish_attempt(self.make_session, aid, self.student_id)
        rid = retry_attempt(self.make_session, aid, self.student_id)
        self.assertNotEqual(rid, aid)
        with self.make_session() as session:
            retry = session.get(Attempt, rid)
            self.assertEqual(retry.retry_of_id, aid)
            self.assertIsNone(retry.finished_at)
            self.assertEqual(retry.pinned_lesson_version_id,
                             self.lesson_version_id)
            pins = list(session.scalars(
                select(AttemptPin.stage_version_id).where(
                    AttemptPin.attempt_id == rid)))
            self.assertEqual(pins, [self.stage_version_id])
        with self.assertRaises(PublicationError) as ctx:
            retry_attempt(self.make_session, aid, self.other_id)
        self.assertEqual(ctx.exception.code, "forbidden")


if __name__ == "__main__":
    unittest.main()
