"""Tests for teacher directives and scoped briefs (SCRUM-123, SCRUM-17)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "database"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from DataModels import (  # noqa: E402
    AppUser,
    Base,
    Classroom,
    Directive,
    DirectiveKind,
    Lesson,
    LessonVersion,
    Membership,
    MembershipStatus,
    School,
    UserRole,
    VersionStatus,
)
from evolvingclass_service import (  # noqa: E402
    PublicationError,
    create_steer_directive,
    deactivate_directive,
    submit_brief,
    update_directive,
)


class DirectiveTestCase(unittest.TestCase):
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
            other = School(name="Other School")
            session.add_all([school, other])
            session.flush()
            room = Classroom(school_id=school.id, name="Room 1")
            session.add(room)
            session.flush()
            teacher = AppUser(role=UserRole.teacher, display_name="T",
                              login_ref="teacher-1")
            student = AppUser(role=UserRole.student, display_name="S",
                              login_ref="student-1")
            outsider = AppUser(role=UserRole.student, display_name="O",
                               login_ref="student-2")
            session.add_all([teacher, student, outsider])
            session.flush()
            session.add_all([
                Membership(user_id=teacher.id, classroom_id=room.id,
                           status=MembershipStatus.active),
                Membership(user_id=student.id, classroom_id=room.id,
                           status=MembershipStatus.active),
                Membership(user_id=outsider.id, school_id=other.id,
                           status=MembershipStatus.active),
            ])
            lesson = Lesson(school_id=school.id, classroom_id=room.id,
                            subject="science", title="L")
            session.add(lesson)
            session.flush()
            self.lesson_id = lesson.id
            self.teacher_id = teacher.id
            self.student_id = student.id
            self.outsider_id = outsider.id

    def _get(self, directive_id):
        with self.make_session() as session:
            directive = session.get(Directive, directive_id)
            return {
                "lesson_id": directive.lesson_id,
                "student_id": directive.student_id,
                "kind": directive.kind,
                "focus": directive.focus,
                "constraints": directive.constraints,
                "priority": directive.priority,
                "author_id": directive.author_id,
                "active": directive.active,
            }

    def test_create_class_wide_steer(self):
        did = create_steer_directive(
            self.make_session, lesson_id=self.lesson_id,
            actor_id=self.teacher_id, focus="Slow down.",
            constraints={"pace": "slow"}, priority=2)
        self.assertEqual(self._get(did), {
            "lesson_id": self.lesson_id, "student_id": None,
            "kind": DirectiveKind.steer, "focus": "Slow down.",
            "constraints": {"pace": "slow"}, "priority": 2,
            "author_id": self.teacher_id, "active": True})

    def test_create_per_student_steer(self):
        did = create_steer_directive(
            self.make_session, lesson_id=self.lesson_id,
            actor_id=self.teacher_id, focus="Extra time.",
            student_id=self.student_id)
        row = self._get(did)
        self.assertEqual(row["student_id"], self.student_id)
        self.assertEqual(row["kind"], DirectiveKind.steer)

    def test_targeting_outside_classroom_rejected(self):
        with self.assertRaises(PublicationError) as ctx:
            create_steer_directive(
                self.make_session, lesson_id=self.lesson_id,
                actor_id=self.teacher_id, focus="Nope.",
                student_id=self.outsider_id)
        self.assertEqual(ctx.exception.code, "invalid_scope")
        with self.assertRaises(PublicationError) as ctx:
            create_steer_directive(
                self.make_session, lesson_id=self.lesson_id,
                actor_id=self.teacher_id, focus="Nope.",
                student_id=self.teacher_id)
        self.assertEqual(ctx.exception.code, "invalid_scope")
        with self.assertRaises(PublicationError) as ctx:
            create_steer_directive(
                self.make_session, lesson_id=self.lesson_id,
                actor_id=self.teacher_id, focus="Nope.", student_id=9999)
        self.assertEqual(ctx.exception.code, "not_found")

    def test_create_rejects_bad_actor_lesson_focus(self):
        with self.assertRaises(PublicationError) as ctx:
            create_steer_directive(
                self.make_session, lesson_id=self.lesson_id,
                actor_id=self.student_id, focus="Nope.")
        self.assertEqual(ctx.exception.code, "forbidden")
        with self.assertRaises(PublicationError) as ctx:
            create_steer_directive(
                self.make_session, lesson_id=9999,
                actor_id=self.teacher_id, focus="Nope.")
        self.assertEqual(ctx.exception.code, "not_found")
        with self.assertRaises(PublicationError) as ctx:
            create_steer_directive(
                self.make_session, lesson_id=self.lesson_id,
                actor_id=self.teacher_id, focus="  ")
        self.assertEqual(ctx.exception.code, "invalid_directive")

    def test_update_and_deactivate(self):
        did = create_steer_directive(
            self.make_session, lesson_id=self.lesson_id,
            actor_id=self.teacher_id, focus="Before.")
        update_directive(
            self.make_session, did, self.teacher_id, focus="After.",
            constraints={"pace": "slow"}, priority=5)
        row = self._get(did)
        self.assertEqual(
            (row["focus"], row["constraints"], row["priority"]),
            ("After.", {"pace": "slow"}, 5))
        with self.assertRaises(PublicationError) as ctx:
            update_directive(
                self.make_session, did, self.teacher_id, focus=" ")
        self.assertEqual(ctx.exception.code, "invalid_directive")
        deactivate_directive(self.make_session, did, self.teacher_id)
        self.assertFalse(self._get(did)["active"])
        deactivate_directive(self.make_session, did, self.teacher_id)
        self.assertFalse(self._get(did)["active"])
        with self.assertRaises(PublicationError) as ctx:
            update_directive(
                self.make_session, 9999, self.teacher_id, focus="x")
        self.assertEqual(ctx.exception.code, "not_found")

    def test_brief_with_student_scope_drafts_personal_variant(self):
        classed = submit_brief(
            self.make_session, lesson_id=self.lesson_id,
            actor_id=self.teacher_id, focus="Class brief.")
        personal = submit_brief(
            self.make_session, lesson_id=self.lesson_id,
            actor_id=self.teacher_id, focus="Personal brief.",
            student_id=self.student_id)
        with self.make_session() as session:
            draft = session.get(LessonVersion, personal.lesson_version_id)
            self.assertEqual(draft.student_scope_id, self.student_id)
            self.assertEqual(draft.version_no, 2)
            self.assertEqual(draft.status, VersionStatus.draft)
            other = session.get(LessonVersion, classed.lesson_version_id)
            self.assertIsNone(other.student_scope_id)
            self.assertEqual(other.version_no, 1)
            directive = session.get(Directive, personal.directive_id)
            self.assertEqual(directive.student_id, self.student_id)
        second = submit_brief(
            self.make_session, lesson_id=self.lesson_id,
            actor_id=self.teacher_id, focus="Personal brief two.",
            student_id=self.student_id)
        self.assertEqual(second.version_no, 3)
        with self.assertRaises(PublicationError) as ctx:
            submit_brief(
                self.make_session, lesson_id=self.lesson_id,
                actor_id=self.teacher_id, focus="Nope.",
                student_id=self.outsider_id)
        self.assertEqual(ctx.exception.code, "invalid_scope")


if __name__ == "__main__":
    unittest.main()
