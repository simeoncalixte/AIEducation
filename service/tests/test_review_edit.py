"""Tests for draft structure editing (SCRUM-33).

Stage asset-uses and lesson composition are replace-the-list edits on
drafts: teachers send the full ordered rows, and published rows stay
frozen behind the draft guard.
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
    Asset,
    AssetKind,
    AssetUse,
    AssetVersion,
    Base,
    Classroom,
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
from evolvingclass_service import (  # noqa: E402
    PublicationError,
    update_lesson_composition,
    update_stage_uses,
)


class ReviewEditTestCase(unittest.TestCase):
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
            self.teacher_id = teacher.id
            self.student_id = student.id
            self.lesson_id = lesson.id

    def _asset_version(self, session, kind=AssetKind.prop):
        asset = Asset(kind=kind, title="A",
                      created_by_id=self.teacher_id)
        session.add(asset)
        session.flush()
        version = AssetVersion(
            asset_id=asset.id, version_no=1,
            status=VersionStatus.draft, rationale="r",
            objective_refs=[], content_ref="c", param_schema={})
        session.add(version)
        session.flush()
        return version.id

    def _stage_version(self, session, status=VersionStatus.draft):
        stage = Stage(lesson_id=self.lesson_id, position=1, title="S")
        session.add(stage)
        session.flush()
        version = StageVersion(
            stage_id=stage.id, version_no=1, status=status,
            rationale="r")
        session.add(version)
        session.flush()
        return version.id

    def _lesson_version(self, session, status=VersionStatus.draft,
                        version_no=1):
        version = LessonVersion(
            lesson_id=self.lesson_id, version_no=version_no,
            status=status, rationale="r", objective_refs=[])
        session.add(version)
        session.flush()
        return version.id

    def test_update_stage_uses_replaces_ordered_rows(self):
        with self.make_session() as session, session.begin():
            first = self._asset_version(session)
            second = self._asset_version(session, AssetKind.character)
            vid = self._stage_version(session)
        update_stage_uses(
            self.make_session, vid, self.teacher_id,
            [{"asset_version_id": first, "role": "centerpiece"},
             {"asset_version_id": second, "role": "guide",
              "param_overrides": {"voice": "calm"}}])
        with self.make_session() as session:
            rows = list(session.scalars(
                select(AssetUse)
                .where(AssetUse.stage_version_id == vid)
                .order_by(AssetUse.position)))
            self.assertEqual(
                [(r.asset_version_id, r.role, r.position)
                 for r in rows],
                [(first, "centerpiece", 1), (second, "guide", 2)])
            self.assertEqual(rows[1].param_overrides, {"voice": "calm"})
        update_stage_uses(
            self.make_session, vid, self.teacher_id,
            [{"asset_version_id": second, "role": "solo"}])
        with self.make_session() as session:
            rows = list(session.scalars(
                select(AssetUse)
                .where(AssetUse.stage_version_id == vid)))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].role, "solo")
            self.assertEqual(rows[0].position, 1)

    def test_update_stage_uses_rejections(self):
        with self.make_session() as session, session.begin():
            vid = self._stage_version(session)
            live = self._stage_version(
                session, status=VersionStatus.published)
            asset = self._asset_version(session)
        with self.assertRaises(PublicationError) as ctx:
            update_stage_uses(
                self.make_session, 9999, self.teacher_id, [])
        self.assertEqual(ctx.exception.code, "not_found")
        with self.assertRaises(PublicationError) as ctx:
            update_stage_uses(
                self.make_session, live, self.teacher_id, [])
        self.assertEqual(ctx.exception.code, "not_draft")
        with self.assertRaises(PublicationError) as ctx:
            update_stage_uses(
                self.make_session, vid, self.student_id, [])
        self.assertEqual(ctx.exception.code, "forbidden")
        with self.assertRaises(PublicationError) as ctx:
            update_stage_uses(
                self.make_session, vid, self.teacher_id,
                [{"asset_version_id": 9999, "role": "prop"}])
        self.assertEqual(ctx.exception.code, "not_found")
        for bad in ("nope",
                    [{"role": "prop"}],
                    [{"asset_version_id": asset, "role": "  "}],
                    [{"asset_version_id": asset}]):
            with self.assertRaises(PublicationError) as ctx:
                update_stage_uses(
                    self.make_session, vid, self.teacher_id, bad)
            self.assertEqual(ctx.exception.code, "invalid_edit", bad)

    def test_update_lesson_composition_replaces_ordered_pins(self):
        with self.make_session() as session, session.begin():
            first = self._stage_version(session)
            second = self._stage_version(session)
            vid = self._lesson_version(session)
        update_lesson_composition(
            self.make_session, vid, self.teacher_id,
            [{"stage_version_id": first},
             {"stage_version_id": second, "required": False}])
        with self.make_session() as session:
            pins = list(session.scalars(
                select(LessonVersionStage)
                .where(LessonVersionStage.lesson_version_id == vid)
                .order_by(LessonVersionStage.position)))
            self.assertEqual(
                [(p.stage_version_id, p.position, p.required)
                 for p in pins],
                [(first, 1, True), (second, 2, False)])
        update_lesson_composition(
            self.make_session, vid, self.teacher_id,
            [{"stage_version_id": second}])
        with self.make_session() as session:
            pins = list(session.scalars(
                select(LessonVersionStage)
                .where(LessonVersionStage.lesson_version_id == vid)))
            self.assertEqual(
                [(p.stage_version_id, p.position) for p in pins],
                [(second, 1)])

    def test_update_lesson_composition_rejections(self):
        with self.make_session() as session, session.begin():
            vid = self._lesson_version(session)
            live = self._lesson_version(
                session, status=VersionStatus.published, version_no=2)
            stage = self._stage_version(session)
        with self.assertRaises(PublicationError) as ctx:
            update_lesson_composition(
                self.make_session, 9999, self.teacher_id, [])
        self.assertEqual(ctx.exception.code, "not_found")
        with self.assertRaises(PublicationError) as ctx:
            update_lesson_composition(
                self.make_session, live, self.teacher_id, [])
        self.assertEqual(ctx.exception.code, "not_draft")
        with self.assertRaises(PublicationError) as ctx:
            update_lesson_composition(
                self.make_session, vid, self.student_id, [])
        self.assertEqual(ctx.exception.code, "forbidden")
        with self.assertRaises(PublicationError) as ctx:
            update_lesson_composition(
                self.make_session, vid, self.teacher_id,
                [{"stage_version_id": 9999}])
        self.assertEqual(ctx.exception.code, "not_found")
        for bad in ("nope",
                    [{"required": True}],
                    [{"stage_version_id": stage, "required": "yes"}],
                    [{"stage_version_id": stage},
                     {"stage_version_id": stage}]):
            with self.assertRaises(PublicationError) as ctx:
                update_lesson_composition(
                    self.make_session, vid, self.teacher_id, bad)
            self.assertEqual(ctx.exception.code, "invalid_edit", bad)


if __name__ == "__main__":
    unittest.main()
