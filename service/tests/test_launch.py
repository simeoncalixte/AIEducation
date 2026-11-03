"""Tests for launch capability matching (SCRUM-39).

Scene requirements are checked against reported device capabilities
before launch; each routing decision is logged as a server
``launch-decision`` event on the attempt.
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
    Assignment,
    Attempt,
    Base,
    Classroom,
    Device,
    DeviceCapability,
    EventOrigin,
    ExperienceEvent,
    Lesson,
    LessonVersion,
    LessonVersionStage,
    Membership,
    MembershipStatus,
    SceneRequirement,
    School,
    Stage,
    StageVersion,
    UserRole,
    VersionStatus,
)
from evolvingclass_service import (  # noqa: E402
    PublicationError,
    start_attempt,
)
from evolvingclass_service.launch import (  # noqa: E402
    decide_launch,
    list_launch_decisions,
    match_capabilities,
    register_device,
    report_device_capabilities,
)


class MatchCapabilitiesTestCase(unittest.TestCase):
    def test_all_met_matches(self):
        found = match_capabilities(
            ["webxr", "plane-detection"],
            ["webxr"], ["plane-detection"])
        self.assertEqual(found["missing_required"], [])
        self.assertEqual(found["missing_preferred"], [])

    def test_missing_required_and_preferred_listed(self):
        found = match_capabilities(
            ["webxr"], ["webxr", "hand-tracking"], ["plane-detection"])
        self.assertEqual(found["missing_required"], ["hand-tracking"])
        self.assertEqual(found["missing_preferred"], ["plane-detection"])

    def test_no_requirements_matches(self):
        found = match_capabilities([], [], [])
        self.assertEqual(found["missing_required"], [])
        self.assertEqual(found["missing_preferred"], [])

    def test_extra_capabilities_ignored(self):
        found = match_capabilities(["webxr", "gpu-high"], ["webxr"], [])
        self.assertEqual(found["missing_required"], [])


class LaunchTestCase(unittest.TestCase):
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
            spare_v = StageVersion(stage_id=stage.id, version_no=2,
                                   status=VersionStatus.published,
                                   rationale="r")
            session.add(spare_v)
            session.flush()
            session.add_all([
                SceneRequirement(stage_version_id=stage_v.id,
                                 capability="webxr", required=True),
                SceneRequirement(stage_version_id=stage_v.id,
                                 capability="plane-detection",
                                 required=False),
            ])
            assignment = Assignment(
                lesson_id=lesson.id, classroom_id=room.id,
                assigned_by_id=teacher.id)
            session.add(assignment)
            session.flush()
            self.assignment_id = assignment.id
            self.stage_version_id = stage_v.id
            self.spare_version_id = spare_v.id
            self.teacher_id = teacher.id
            self.student_id = student.id
            self.other_id = other.id
        self.attempt_id = start_attempt(
            self.make_session, self.assignment_id, self.student_id)

    def test_register_and_report_device(self):
        device_id = register_device(
            self.make_session, self.student_id, "Quest 3")
        reported = report_device_capabilities(
            self.make_session, device_id, self.student_id,
            ["webxr", "plane-detection"])
        self.assertEqual(reported, ["plane-detection", "webxr"])
        with self.make_session() as session:
            device = session.get(Device, device_id)
            self.assertEqual(device.student_id, self.student_id)
            caps = sorted(c.capability for c in device.capabilities)
            self.assertEqual(caps, ["plane-detection", "webxr"])

    def test_report_updates_detail_and_rejects_blanks(self):
        device_id = register_device(
            self.make_session, self.student_id, "Quest 3")
        report_device_capabilities(
            self.make_session, device_id, self.student_id,
            [{"capability": "webxr", "detail": "v1"}])
        report_device_capabilities(
            self.make_session, device_id, self.student_id,
            [{"capability": "webxr", "detail": "v2"}])
        with self.make_session() as session:
            rows = list(session.scalars(
                select(DeviceCapability).where(
                    DeviceCapability.device_id == device_id)))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].detail, "v2")
        with self.assertRaises(PublicationError) as ctx:
            report_device_capabilities(
                self.make_session, device_id, self.student_id, ["  "])
        self.assertEqual(ctx.exception.code, "invalid_play")

    def test_device_access_is_owner_only(self):
        device_id = register_device(
            self.make_session, self.student_id, "Quest 3")
        with self.assertRaises(PublicationError) as ctx:
            report_device_capabilities(
                self.make_session, device_id, self.other_id, ["webxr"])
        self.assertEqual(ctx.exception.code, "forbidden")
        with self.assertRaises(PublicationError) as ctx:
            report_device_capabilities(
                self.make_session, 9999, self.student_id, ["webxr"])
        self.assertEqual(ctx.exception.code, "not_found")
        with self.assertRaises(PublicationError) as ctx:
            register_device(self.make_session, self.teacher_id, "Lab")
        self.assertEqual(ctx.exception.code, "forbidden")
        with self.assertRaises(PublicationError) as ctx:
            register_device(self.make_session, self.student_id, "  ")
        self.assertEqual(ctx.exception.code, "invalid_play")

    def test_launch_routes_immersive_when_requirements_met(self):
        decision = decide_launch(
            self.make_session, self.attempt_id, self.student_id,
            self.stage_version_id, ["webxr", "plane-detection"])
        self.assertEqual(decision["route"], "immersive")
        self.assertEqual(decision["missing_required"], [])
        self.assertEqual(decision["missing_preferred"], [])
        self.assertEqual(decision["stage_version_id"],
                         self.stage_version_id)
        self.assertIsNone(decision["device_id"])

    def test_launch_falls_back_when_required_missing(self):
        decision = decide_launch(
            self.make_session, self.attempt_id, self.student_id,
            self.stage_version_id, ["plane-detection"])
        self.assertEqual(decision["route"], "web")
        self.assertEqual(decision["missing_required"], ["webxr"])
        self.assertIn("webxr", decision["reason"])

    def test_launch_stays_immersive_when_only_preferred_missing(self):
        decision = decide_launch(
            self.make_session, self.attempt_id, self.student_id,
            self.stage_version_id, ["webxr"])
        self.assertEqual(decision["route"], "immersive")
        self.assertEqual(decision["missing_preferred"],
                         ["plane-detection"])
        self.assertIn("plane-detection", decision["reason"])

    def test_launch_reads_stored_device_capabilities(self):
        device_id = register_device(
            self.make_session, self.student_id, "Quest 3")
        report_device_capabilities(
            self.make_session, device_id, self.student_id, ["webxr"])
        decision = decide_launch(
            self.make_session, self.attempt_id, self.student_id,
            self.stage_version_id, ["plane-detection"],
            device_id=device_id)
        self.assertEqual(decision["route"], "immersive")
        self.assertEqual(decision["device_id"], device_id)
        stored_only = decide_launch(
            self.make_session, self.attempt_id, self.student_id,
            self.stage_version_id, device_id=device_id)
        self.assertEqual(stored_only["route"], "immersive")
        self.assertEqual(stored_only["missing_preferred"],
                         ["plane-detection"])

    def test_launch_logs_routing_decision_per_launch(self):
        first = decide_launch(
            self.make_session, self.attempt_id, self.student_id,
            self.stage_version_id, ["webxr"])
        second = decide_launch(
            self.make_session, self.attempt_id, self.student_id,
            self.stage_version_id, [])
        self.assertNotEqual(second["event_id"], first["event_id"])
        with self.make_session() as session:
            rows = list(session.scalars(
                select(ExperienceEvent)
                .where(ExperienceEvent.attempt_id == self.attempt_id,
                       ExperienceEvent.verb == "launch-decision")
                .order_by(ExperienceEvent.sequence_no)))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0].origin, EventOrigin.server)
            self.assertEqual(rows[0].actor_id, self.student_id)
            self.assertEqual(rows[0].stage_version_id,
                             self.stage_version_id)
            self.assertEqual(rows[0].payload["route"], "immersive")
            self.assertEqual(rows[1].payload["route"], "web")

    def test_launch_history_lists_decisions_in_order(self):
        decide_launch(
            self.make_session, self.attempt_id, self.student_id,
            self.stage_version_id, ["webxr"])
        decide_launch(
            self.make_session, self.attempt_id, self.student_id,
            self.stage_version_id, [])
        history = list_launch_decisions(
            self.make_session, self.attempt_id, self.student_id)
        self.assertEqual([h["route"] for h in history],
                         ["immersive", "web"])
        self.assertEqual(history[0]["stage_version_id"],
                         self.stage_version_id)
        self.assertLess(history[0]["sequence_no"],
                        history[1]["sequence_no"])
        with self.assertRaises(PublicationError) as ctx:
            list_launch_decisions(
                self.make_session, self.attempt_id, self.other_id)
        self.assertEqual(ctx.exception.code, "forbidden")

    def test_launch_rejections(self):
        with self.assertRaises(PublicationError) as ctx:
            decide_launch(
                self.make_session, 9999, self.student_id,
                self.stage_version_id, ["webxr"])
        self.assertEqual(ctx.exception.code, "not_found")
        with self.assertRaises(PublicationError) as ctx:
            decide_launch(
                self.make_session, self.attempt_id, self.other_id,
                self.stage_version_id, ["webxr"])
        self.assertEqual(ctx.exception.code, "forbidden")
        with self.assertRaises(PublicationError) as ctx:
            decide_launch(
                self.make_session, self.attempt_id, self.student_id,
                9999, ["webxr"])
        self.assertEqual(ctx.exception.code, "not_found")
        with self.assertRaises(PublicationError) as ctx:
            decide_launch(
                self.make_session, self.attempt_id, self.student_id,
                self.spare_version_id, ["webxr"])
        self.assertEqual(ctx.exception.code, "invalid_play")
        with self.assertRaises(PublicationError) as ctx:
            decide_launch(
                self.make_session, self.attempt_id, self.student_id,
                self.stage_version_id)
        self.assertEqual(ctx.exception.code, "invalid_play")
        with self.assertRaises(PublicationError) as ctx:
            decide_launch(
                self.make_session, self.attempt_id, self.student_id,
                self.stage_version_id, ["  "])
        self.assertEqual(ctx.exception.code, "invalid_play")
        with self.assertRaises(PublicationError) as ctx:
            decide_launch(
                self.make_session, self.attempt_id, self.student_id,
                self.stage_version_id, ["webxr"], device_id=9999)
        self.assertEqual(ctx.exception.code, "not_found")


if __name__ == "__main__":
    unittest.main()
