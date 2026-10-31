"""Tests for publish-time preview finalization (SCRUM-28)."""

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
    Approval,
    Asset,
    AssetKind,
    AssetVersion,
    Base,
    Classroom,
    Decision,
    Lesson,
    Membership,
    MembershipStatus,
    PreviewArtifact,
    PreviewKind,
    School,
    Stage,
    StageVersion,
    UserRole,
    VersionStatus,
)
from evolvingclass_service import (  # noqa: E402
    publish_asset_version,
    publish_stage_version,
)


class PreviewFinalizeTestCase(unittest.TestCase):
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
            session.add(teacher)
            session.flush()
            session.add(Membership(user_id=teacher.id,
                                   classroom_id=room.id,
                                   status=MembershipStatus.active))
            lesson = Lesson(school_id=school.id, classroom_id=room.id,
                            subject="science", title="L")
            session.add(lesson)
            session.flush()
            self.teacher_id = teacher.id
            self.lesson_id = lesson.id
            self.school_id = school.id

    def _asset_version(self):
        with self.make_session() as session, session.begin():
            asset = Asset(kind=AssetKind.prop, title="A",
                          created_by_id=self.teacher_id,
                          school_id=self.school_id)
            session.add(asset)
            session.flush()
            version = AssetVersion(
                asset_id=asset.id, version_no=1,
                status=VersionStatus.draft, rationale="r",
                objective_refs=[], content_ref="c", param_schema={})
            session.add(version)
            session.flush()
            session.add(Approval(asset_version_id=version.id,
                                 actor_id=self.teacher_id,
                                 decision=Decision.approved, rationale="ok"))
            return version.id

    def _stage_version(self):
        with self.make_session() as session, session.begin():
            stage = Stage(lesson_id=self.lesson_id, position=1, title="S")
            session.add(stage)
            session.flush()
            version = StageVersion(stage_id=stage.id, version_no=1,
                                   status=VersionStatus.draft, rationale="r")
            session.add(version)
            session.flush()
            session.add(Approval(stage_version_id=version.id,
                                 actor_id=self.teacher_id,
                                 decision=Decision.approved, rationale="ok"))
            return version.id

    def _artifacts(self, kind, version_id):
        with self.make_session() as session:
            return list(session.query(PreviewArtifact).filter_by(
                **{f"{kind}_version_id": version_id}).all())

    def test_publish_asset_pins_finalized_preview(self):
        vid = self._asset_version()
        calls = []
        publish_asset_version(
            self.make_session, vid, self.teacher_id, "go",
            finalize_preview=lambda k, v: calls.append((k, v)) or (
                "poster", "7/v1_poster.svg"))
        self.assertEqual(calls, [("asset", vid)])
        rows = self._artifacts("asset", vid)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, PreviewKind.poster)
        self.assertEqual(rows[0].storage_ref, "7/v1_poster.svg")
        self.assertIsNotNone(rows[0].rendered_at)

    def test_publish_without_finalizer_writes_no_preview(self):
        vid = self._asset_version()
        publish_asset_version(self.make_session, vid, self.teacher_id, "go")
        self.assertEqual(self._artifacts("asset", vid), [])

    def test_finalize_skipped_when_preview_exists(self):
        vid = self._asset_version()
        with self.make_session() as session, session.begin():
            session.add(PreviewArtifact(
                asset_version_id=vid, kind=PreviewKind.poster,
                storage_ref="7/v1_poster.svg"))
        calls = []
        publish_asset_version(
            self.make_session, vid, self.teacher_id, "go",
            finalize_preview=lambda k, v: calls.append((k, v)))
        self.assertEqual(calls, [])
        self.assertEqual(len(self._artifacts("asset", vid)), 1)

    def test_publish_stage_pins_finalized_preview(self):
        vid = self._stage_version()
        publish_stage_version(
            self.make_session, vid, self.teacher_id, "go",
            finalize_preview=lambda k, v: ("poster", "stage/3/v1_poster.svg"))
        rows = self._artifacts("stage", vid)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].storage_ref, "stage/3/v1_poster.svg")


if __name__ == "__main__":
    unittest.main()
