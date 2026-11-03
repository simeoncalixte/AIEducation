"""Tests for verdict overrides and misconception flags (SCRUM-19)."""

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
    MentalModel,
    Misconception,
    School,
    Stage,
    StageVersion,
    UserRole,
    VerdictOverride,
    VersionStatus,
)
from evolvingclass_service import (  # noqa: E402
    PublicationError,
    flag_misconception,
    record_teacher_evaluation,
    record_verdict_override,
)


class FeedbackTestCase(unittest.TestCase):
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
            session.add(Membership(user_id=teacher.id,
                                   classroom_id=room.id,
                                   status=MembershipStatus.active))
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
            model = MentalModel(lesson_version_id=lesson_v.id,
                                position=1, statement="Magma rises.")
            session.add(model)
            session.flush()
            misconception = Misconception(
                mental_model_id=model.id, description="Lava is unrelated.",
                probe_notes="Ask.")
            session.add(misconception)
            session.flush()
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
            goal = Goal(challenge_version_id=challenge.id, key="crater",
                        rule={"verb": "x"}, evaluation=GoalEvaluation.deterministic,
                        template_ref="t")
            session.add(goal)
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
            verdict = ExperienceEvent(
                attempt_id=attempt.id, client_event_id="v1",
                sequence_no=1, origin=EventOrigin.server,
                actor_id=teacher.id, verb="goal-verdict",
                object_type="goal", object_ref="crater", goal_id=goal.id,
                payload={"passed": False})
            session.add(verdict)
            session.flush()
            plain = ExperienceEvent(
                attempt_id=attempt.id, client_event_id="p1",
                sequence_no=2, origin=EventOrigin.client,
                actor_id=student.id, verb="attempted",
                object_type="challenge", object_ref="c", payload={})
            session.add(plain)
            session.flush()
            self.teacher_id = teacher.id
            self.student_id = student.id
            self.attempt_id = attempt.id
            self.verdict_id = verdict.id
            self.plain_id = plain.id
            self.misconception_id = misconception.id

    def test_override_stores_correction_and_reason(self):
        oid = record_verdict_override(
            self.make_session, self.verdict_id, self.teacher_id,
            reason="Reread the evidence.", corrected_passed=True,
            corrected_score=0.8)
        with self.make_session() as session:
            override = session.get(VerdictOverride, oid)
            self.assertEqual(override.verdict_event_id, self.verdict_id)
            self.assertEqual(override.teacher_id, self.teacher_id)
            self.assertEqual(override.reason, "Reread the evidence.")
            self.assertTrue(override.corrected_passed)
            self.assertEqual(override.corrected_score, 0.8)
            self.assertIsNotNone(override.created_at)

    def test_override_history_latest_wins(self):
        record_verdict_override(
            self.make_session, self.verdict_id, self.teacher_id,
            reason="First read.", corrected_passed=True)
        record_verdict_override(
            self.make_session, self.verdict_id, self.teacher_id,
            reason="Second read.", corrected_passed=False)
        with self.make_session() as session:
            rows = list(session.scalars(
                select(VerdictOverride)
                .where(VerdictOverride.verdict_event_id == self.verdict_id)
                .order_by(VerdictOverride.id)))
            self.assertEqual(
                [r.reason for r in rows], ["First read.", "Second read."])
            self.assertFalse(rows[-1].corrected_passed)

    def test_override_rejections(self):
        with self.assertRaises(PublicationError) as ctx:
            record_verdict_override(
                self.make_session, 9999, self.teacher_id,
                reason="x", corrected_passed=True)
        self.assertEqual(ctx.exception.code, "not_found")
        with self.assertRaises(PublicationError) as ctx:
            record_verdict_override(
                self.make_session, self.plain_id, self.teacher_id,
                reason="x", corrected_passed=True)
        self.assertEqual(ctx.exception.code, "invalid_feedback")
        with self.assertRaises(PublicationError) as ctx:
            record_verdict_override(
                self.make_session, self.verdict_id, self.teacher_id,
                reason="  ", corrected_passed=True)
        self.assertEqual(ctx.exception.code, "invalid_feedback")
        with self.assertRaises(PublicationError) as ctx:
            record_verdict_override(
                self.make_session, self.verdict_id, self.teacher_id,
                reason="x", corrected_passed=True, corrected_score=1.5)
        self.assertEqual(ctx.exception.code, "invalid_feedback")
        with self.assertRaises(PublicationError) as ctx:
            record_verdict_override(
                self.make_session, self.verdict_id, self.student_id,
                reason="x", corrected_passed=True)
        self.assertEqual(ctx.exception.code, "forbidden")

    def test_flag_creates_teacher_event(self):
        eid = flag_misconception(
            self.make_session, self.attempt_id, self.teacher_id,
            misconception_id=self.misconception_id, note="Said lava.")
        with self.make_session() as session:
            event = session.get(ExperienceEvent, eid)
            self.assertEqual(event.attempt_id, self.attempt_id)
            self.assertEqual(event.origin, EventOrigin.server)
            self.assertEqual(event.actor_id, self.teacher_id)
            self.assertEqual(event.verb, "misconception-flagged")
            self.assertEqual(event.object_type, "misconception")
            self.assertEqual(event.sequence_no, 3)
            self.assertEqual(
                event.payload,
                {"note": "Said lava.",
                 "misconception_id": self.misconception_id})

    def test_flag_note_only_and_rejections(self):
        eid = flag_misconception(
            self.make_session, self.attempt_id, self.teacher_id,
            note="General confusion.")
        with self.make_session() as session:
            event = session.get(ExperienceEvent, eid)
            self.assertEqual(event.object_ref, "general")
        with self.assertRaises(PublicationError) as ctx:
            flag_misconception(
                self.make_session, self.attempt_id, self.teacher_id)
        self.assertEqual(ctx.exception.code, "invalid_feedback")
        with self.assertRaises(PublicationError) as ctx:
            flag_misconception(
                self.make_session, 9999, self.teacher_id, note="x")
        self.assertEqual(ctx.exception.code, "not_found")
        with self.assertRaises(PublicationError) as ctx:
            flag_misconception(
                self.make_session, self.attempt_id, self.teacher_id,
                misconception_id=9999)
        self.assertEqual(ctx.exception.code, "not_found")
        with self.assertRaises(PublicationError) as ctx:
            flag_misconception(
                self.make_session, self.attempt_id, self.student_id,
                note="x")
        self.assertEqual(ctx.exception.code, "forbidden")

    def _scoped_teacher_goal(self, key="explain"):
        """Teacher goal on a challenge pinned in the attempt's lesson."""
        with self.make_session() as session, session.begin():
            challenge_id = session.scalar(select(AssetVersion.id))
            lesson_v_id = session.scalar(select(LessonVersion.id))
            lesson_id = session.scalar(select(Lesson.id))
            stage = Stage(lesson_id=lesson_id, position=1, title="S")
            session.add(stage)
            session.flush()
            stage_v = StageVersion(
                stage_id=stage.id, version_no=1,
                status=VersionStatus.published, rationale="r")
            session.add(stage_v)
            session.flush()
            session.add(AssetUse(
                asset_version_id=challenge_id,
                stage_version_id=stage_v.id, position=1,
                role="task", param_overrides={}))
            session.add(LessonVersionStage(
                lesson_version_id=lesson_v_id,
                stage_version_id=stage_v.id, position=1))
            goal = Goal(
                challenge_version_id=challenge_id, key=key, rule={},
                evaluation=GoalEvaluation.teacher,
                rubric={"criteria": ["names magma"]},
                template_ref="t")
            session.add(goal)
            session.flush()
            return goal.id

    def test_teacher_evaluation_records_server_event(self):
        goal_id = self._scoped_teacher_goal()
        eid = record_teacher_evaluation(
            self.make_session, self.attempt_id, goal_id,
            self.teacher_id, True, rationale="Names magma.")
        with self.make_session() as session:
            event = session.get(ExperienceEvent, eid)
            self.assertEqual(event.attempt_id, self.attempt_id)
            self.assertEqual(event.origin, EventOrigin.server)
            self.assertEqual(event.actor_id, self.teacher_id)
            self.assertEqual(event.verb, "teacher-evaluation")
            self.assertEqual(event.object_type, "goal")
            self.assertEqual(event.object_ref, "explain")
            self.assertEqual(event.goal_id, goal_id)
            self.assertIsNotNone(event.challenge_version_id)
            self.assertEqual(event.sequence_no, 3)
            self.assertEqual(
                event.payload,
                {"passed": True, "goal_key": "explain",
                 "rationale": "Names magma."})

    def test_teacher_evaluation_rejections(self):
        goal_id = self._scoped_teacher_goal()
        deterministic_id = None
        with self.make_session() as session:
            deterministic_id = session.scalar(
                select(Goal.id).where(
                    Goal.evaluation == GoalEvaluation.deterministic))
        with self.assertRaises(PublicationError) as ctx:
            record_teacher_evaluation(
                self.make_session, 9999, goal_id, self.teacher_id,
                True)
        self.assertEqual(ctx.exception.code, "not_found")
        with self.assertRaises(PublicationError) as ctx:
            record_teacher_evaluation(
                self.make_session, self.attempt_id, 9999,
                self.teacher_id, True)
        self.assertEqual(ctx.exception.code, "not_found")
        with self.assertRaises(PublicationError) as ctx:
            record_teacher_evaluation(
                self.make_session, self.attempt_id,
                deterministic_id, self.teacher_id, True)
        self.assertEqual(ctx.exception.code, "invalid_feedback")
        with self.assertRaises(PublicationError) as ctx:
            record_teacher_evaluation(
                self.make_session, self.attempt_id, goal_id,
                self.student_id, True)
        self.assertEqual(ctx.exception.code, "forbidden")
        with self.assertRaises(PublicationError) as ctx:
            record_teacher_evaluation(
                self.make_session, self.attempt_id, goal_id,
                self.teacher_id, "pass")
        self.assertEqual(ctx.exception.code, "invalid_feedback")
        record_teacher_evaluation(
            self.make_session, self.attempt_id, goal_id,
            self.teacher_id, True)
        with self.assertRaises(PublicationError) as ctx:
            record_teacher_evaluation(
                self.make_session, self.attempt_id, goal_id,
                self.teacher_id, False)
        self.assertEqual(ctx.exception.code, "invalid_feedback")

    def test_teacher_evaluation_rejects_out_of_scope_goal(self):
        with self.make_session() as session, session.begin():
            other = Asset(kind=AssetKind.challenge, title="Other",
                          created_by_id=self.teacher_id)
            session.add(other)
            session.flush()
            challenge = AssetVersion(
                asset_id=other.id, version_no=1,
                status=VersionStatus.published, rationale="r",
                objective_refs=[], content_ref="c", param_schema={})
            session.add(challenge)
            session.flush()
            goal = Goal(challenge_version_id=challenge.id,
                        key="elsewhere", rule={},
                        evaluation=GoalEvaluation.teacher,
                        rubric={"criteria": ["x"]}, template_ref="t")
            session.add(goal)
            session.flush()
            goal_id = goal.id
        with self.assertRaises(PublicationError) as ctx:
            record_teacher_evaluation(
                self.make_session, self.attempt_id, goal_id,
                self.teacher_id, True)
        self.assertEqual(ctx.exception.code, "invalid_scope")


if __name__ == "__main__":
    unittest.main()
