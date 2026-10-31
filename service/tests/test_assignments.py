"""Tests for lesson assignments (SCRUM-125, SCRUM-18)."""

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
    Assignment,
    Base,
    Classroom,
    Lesson,
    Membership,
    MembershipStatus,
    School,
    UserRole,
)
from evolvingclass_service import PublicationError, assign_lesson  # noqa: E402


class AssignTestCase(unittest.TestCase):
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
            far = Classroom(school_id=other.id, name="Far Room")
            session.add_all([room, far])
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
            self.room_id = room.id
            self.far_id = far.id
            self.teacher_id = teacher.id
            self.student_id = student.id
            self.outsider_id = outsider.id

    def _get(self, assignment_id):
        with self.make_session() as session:
            assignment = session.get(Assignment, assignment_id)
            return {
                "lesson_id": assignment.lesson_id,
                "classroom_id": assignment.classroom_id,
                "student_id": assignment.student_id,
                "assigned_by_id": assignment.assigned_by_id,
            }

    def test_assign_to_classroom(self):
        aid = assign_lesson(
            self.make_session, self.lesson_id, self.teacher_id,
            classroom_id=self.room_id)
        self.assertEqual(self._get(aid), {
            "lesson_id": self.lesson_id, "classroom_id": self.room_id,
            "student_id": None, "assigned_by_id": self.teacher_id})

    def test_assign_to_student(self):
        aid = assign_lesson(
            self.make_session, self.lesson_id, self.teacher_id,
            student_id=self.student_id)
        row = self._get(aid)
        self.assertEqual(row["student_id"], self.student_id)
        self.assertIsNone(row["classroom_id"])

    def test_assign_is_idempotent_per_target(self):
        first = assign_lesson(
            self.make_session, self.lesson_id, self.teacher_id,
            classroom_id=self.room_id)
        second = assign_lesson(
            self.make_session, self.lesson_id, self.teacher_id,
            classroom_id=self.room_id)
        self.assertEqual(first, second)
        with self.make_session() as session:
            self.assertEqual(session.query(Assignment).count(), 1)

    def test_targeting_rules(self):
        with self.assertRaises(PublicationError) as ctx:
            assign_lesson(
                self.make_session, self.lesson_id, self.teacher_id)
        self.assertEqual(ctx.exception.code, "invalid_scope")
        with self.assertRaises(PublicationError) as ctx:
            assign_lesson(
                self.make_session, self.lesson_id, self.teacher_id,
                classroom_id=self.room_id, student_id=self.student_id)
        self.assertEqual(ctx.exception.code, "invalid_scope")
        with self.assertRaises(PublicationError) as ctx:
            assign_lesson(
                self.make_session, self.lesson_id, self.teacher_id,
                classroom_id=self.far_id)
        self.assertEqual(ctx.exception.code, "invalid_scope")
        with self.assertRaises(PublicationError) as ctx:
            assign_lesson(
                self.make_session, self.lesson_id, self.teacher_id,
                classroom_id=9999)
        self.assertEqual(ctx.exception.code, "not_found")
        with self.assertRaises(PublicationError) as ctx:
            assign_lesson(
                self.make_session, self.lesson_id, self.teacher_id,
                student_id=self.outsider_id)
        self.assertEqual(ctx.exception.code, "invalid_scope")

    def test_actor_and_lesson_rules(self):
        with self.assertRaises(PublicationError) as ctx:
            assign_lesson(
                self.make_session, 9999, self.teacher_id,
                classroom_id=self.room_id)
        self.assertEqual(ctx.exception.code, "not_found")
        with self.assertRaises(PublicationError) as ctx:
            assign_lesson(
                self.make_session, self.lesson_id, self.student_id,
                classroom_id=self.room_id)
        self.assertEqual(ctx.exception.code, "forbidden")


if __name__ == "__main__":
    unittest.main()
