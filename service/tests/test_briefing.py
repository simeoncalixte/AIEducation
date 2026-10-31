"""Tests for teacher briefing (SCRUM-15).

A brief form submission persists a directive of kind brief and produces a
lesson draft proposal carrying a rationale and a directive snapshot.
"""

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
    Classroom,
    Directive,
    DirectiveKind,
    GenerationStatus,
    Lesson,
    LessonVersion,
    Membership,
    MembershipStatus,
    MentalModel,
    School,
    UserRole,
    VersionStatus,
)
from evolvingclass_service import PublicationError, submit_brief  # noqa: E402


class BriefingTestCase(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        from DataModels import Base

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
                            subject="science", title="Volcanoes")
            session.add(lesson)
            session.flush()
            self.lesson_id = lesson.id
            self.teacher_id = teacher.id
            self.student_id = student.id

    # -- happy path --------------------------------------------------------

    def test_brief_persists_directive_and_draft(self):
        result = submit_brief(
            self.make_session,
            lesson_id=self.lesson_id,
            actor_id=self.teacher_id,
            objectives=["sci.eruptions"],
            mental_models=["Magma rises through a vent."],
            focus="Cover the three eruption stages in order.",
            constraints={"must_include": ["crater diagram"]},
        )
        with self.make_session() as session:
            directive = session.get(Directive, result.directive_id)
            self.assertEqual(directive.lesson_id, self.lesson_id)
            self.assertEqual(directive.kind, DirectiveKind.brief)
            self.assertIsNone(directive.student_id)
            self.assertEqual(directive.focus,
                             "Cover the three eruption stages in order.")
            self.assertEqual(directive.constraints,
                             {"must_include": ["crater diagram"]})
            self.assertEqual(directive.author_id, self.teacher_id)
            self.assertTrue(directive.active)

            draft = session.get(LessonVersion, result.lesson_version_id)
            self.assertEqual(draft.lesson_id, self.lesson_id)
            self.assertEqual(draft.status, VersionStatus.draft)
            self.assertEqual(draft.version_no, 1)
            self.assertIn("Cover the three eruption stages in order.",
                          draft.rationale)
            self.assertEqual(draft.objective_refs, ["sci.eruptions"])
            snapshot_ids = [d["id"] for d in
                            draft.directive_snapshot["directives"]]
            self.assertIn(directive.id, snapshot_ids)
            self.assertTrue(draft.directive_snapshot["brief"])
            self.assertEqual(draft.generation_run.status,
                             GenerationStatus.completed)

            models = list(session.scalars(
                select(MentalModel)
                .where(MentalModel.lesson_version_id == draft.id)
                .order_by(MentalModel.position)
            ))
            self.assertEqual([m.statement for m in models],
                             ["Magma rises through a vent."])
            self.assertEqual(models[0].position, 1)

    def test_second_brief_increments_version_and_snapshots_both(self):
        first = submit_brief(
            self.make_session, lesson_id=self.lesson_id,
            actor_id=self.teacher_id, focus="First brief.")
        second = submit_brief(
            self.make_session, lesson_id=self.lesson_id,
            actor_id=self.teacher_id, focus="Second brief.")
        self.assertEqual(second.version_no, 2)
        with self.make_session() as session:
            draft = session.get(LessonVersion, second.lesson_version_id)
            snapshot_ids = [d["id"] for d in
                            draft.directive_snapshot["directives"]]
            self.assertEqual(snapshot_ids,
                             [first.directive_id, second.directive_id])

    def test_minimal_brief_allows_empty_lists(self):
        result = submit_brief(
            self.make_session, lesson_id=self.lesson_id,
            actor_id=self.teacher_id, focus="Just a focus.")
        with self.make_session() as session:
            draft = session.get(LessonVersion, result.lesson_version_id)
            self.assertEqual(draft.objective_refs, [])
            self.assertEqual(
                session.scalar(
                    select(MentalModel.id).where(
                        MentalModel.lesson_version_id == draft.id)),
                None)
            directive = session.get(Directive, result.directive_id)
            self.assertEqual(directive.constraints, {})

    # -- rejections ---------------------------------------------------------

    def test_student_cannot_brief(self):
        with self.assertRaises(PublicationError) as ctx:
            submit_brief(
                self.make_session, lesson_id=self.lesson_id,
                actor_id=self.student_id, focus="Nope.")
        self.assertEqual(ctx.exception.code, "forbidden")

    def test_unknown_lesson_rejected(self):
        with self.assertRaises(PublicationError) as ctx:
            submit_brief(
                self.make_session, lesson_id=9999,
                actor_id=self.teacher_id, focus="Nope.")
        self.assertEqual(ctx.exception.code, "not_found")

    def test_blank_focus_rejected_without_side_effects(self):
        with self.assertRaises(PublicationError) as ctx:
            submit_brief(
                self.make_session, lesson_id=self.lesson_id,
                actor_id=self.teacher_id, focus="   ")
        self.assertEqual(ctx.exception.code, "invalid_brief")
        with self.make_session() as session:
            self.assertEqual(
                session.query(Directive).count(), 0)
            self.assertEqual(
                session.query(LessonVersion).count(), 0)


if __name__ == "__main__":
    unittest.main()
