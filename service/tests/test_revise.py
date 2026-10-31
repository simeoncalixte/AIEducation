"""Tests for asset revision (SCRUM-29)."""

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
    AssetTag,
    AssetUse,
    AssetVersion,
    Base,
    Classroom,
    Decision,
    Goal,
    GoalEvaluation,
    Lesson,
    Membership,
    MembershipStatus,
    School,
    Stage,
    StageVersion,
    TagTaxonomy,
    UserRole,
    VersionStatus,
)
from evolvingclass_service import (  # noqa: E402
    PublicationError,
    publish_asset_version,
    retire_asset_version,
    revise_asset_version,
)


class ReviseTestCase(unittest.TestCase):
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
            self.teacher_id = teacher.id
            self.student_id = student.id
            self.school_id = school.id

    def _live_version(self, kind=AssetKind.prop):
        with self.make_session() as session, session.begin():
            asset = Asset(kind=kind, title="A",
                          created_by_id=self.teacher_id,
                          school_id=self.school_id)
            session.add(asset)
            session.flush()
            version = AssetVersion(
                asset_id=asset.id, version_no=1,
                status=VersionStatus.draft, rationale="r",
                objective_refs=["sci.x"], content_ref="c",
                param_schema={"scale": "number"})
            session.add(version)
            session.flush()
            session.add(AssetTag(asset_version_id=version.id,
                                 taxonomy=TagTaxonomy.subject,
                                 value="science"))
            if kind is AssetKind.challenge:
                session.add(Goal(challenge_version_id=version.id,
                                 key="g1", rule={"target": "x"},
                                 evaluation=GoalEvaluation.deterministic,
                                 template_ref="t"))
            session.add(Approval(asset_version_id=version.id,
                                 actor_id=self.teacher_id,
                                 decision=Decision.approved, rationale="ok"))
            vid = version.id
        publish_asset_version(self.make_session, vid, self.teacher_id, "go")
        return vid

    def test_revise_copies_content_tags_and_lineage(self):
        vid = self._live_version()
        new_id = revise_asset_version(
            self.make_session, vid, self.teacher_id, "sharper edges")
        with self.make_session() as session:
            draft = session.get(AssetVersion, new_id)
            self.assertEqual(draft.version_no, 2)
            self.assertEqual(draft.status, VersionStatus.draft)
            self.assertEqual(draft.rationale,
                             "Revision of v1: sharper edges")
            self.assertEqual(draft.objective_refs, ["sci.x"])
            self.assertEqual(draft.content_ref, "c")
            self.assertEqual(draft.param_schema, {"scale": "number"})
            self.assertEqual(
                [(t.taxonomy, t.value) for t in draft.tags],
                [(TagTaxonomy.subject, "science")])
            source = session.get(AssetVersion, vid)
            self.assertEqual(source.status, VersionStatus.published)

    def test_revise_copies_challenge_goals(self):
        vid = self._live_version(kind=AssetKind.challenge)
        new_id = revise_asset_version(
            self.make_session, vid, self.teacher_id, "clearer task")
        with self.make_session() as session:
            goals = session.get(AssetVersion, new_id).goals
            self.assertEqual([(g.key, g.template_ref) for g in goals],
                             [("g1", "t")])

    def test_revise_retired_version(self):
        vid = self._live_version()
        retire_asset_version(self.make_session, vid, self.teacher_id, "old")
        new_id = revise_asset_version(
            self.make_session, vid, self.teacher_id, "second life")
        with self.make_session() as session:
            draft = session.get(AssetVersion, new_id)
            self.assertEqual(draft.version_no, 2)
            self.assertEqual(
                session.get(AssetVersion, vid).status,
                VersionStatus.retired)

    def test_pins_keep_pointing_at_revised_version(self):
        vid = self._live_version()
        with self.make_session() as session, session.begin():
            school_id = self.school_id
            room_id = session.query(Classroom).first().id
            lesson = Lesson(school_id=school_id, classroom_id=room_id,
                            subject="s", title="L")
            session.add(lesson)
            session.flush()
            stage = Stage(lesson_id=lesson.id, position=1, title="S")
            session.add(stage)
            session.flush()
            stage_v = StageVersion(stage_id=stage.id, version_no=1,
                                   status=VersionStatus.draft,
                                   rationale="r")
            session.add(stage_v)
            session.flush()
            session.add(AssetUse(asset_version_id=vid,
                                 stage_version_id=stage_v.id, position=1,
                                 role="prop", param_overrides={}))
        revise_asset_version(self.make_session, vid, self.teacher_id, "fix")
        with self.make_session() as session:
            uses = session.query(AssetUse).all()
            self.assertEqual(len(uses), 1)
            self.assertEqual(uses[0].asset_version_id, vid)

    def test_revise_draft_rejected(self):
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
            vid = version.id
        with self.assertRaises(PublicationError) as ctx:
            revise_asset_version(
                self.make_session, vid, self.teacher_id, "fix")
        self.assertEqual(ctx.exception.code, "not_published")

    def test_revise_unknown_and_student_rejected(self):
        with self.assertRaises(PublicationError) as ctx:
            revise_asset_version(
                self.make_session, 9999, self.teacher_id, "fix")
        self.assertEqual(ctx.exception.code, "not_found")
        vid = self._live_version()
        with self.assertRaises(PublicationError) as ctx:
            revise_asset_version(
                self.make_session, vid, self.student_id, "fix")
        self.assertEqual(ctx.exception.code, "forbidden")


if __name__ == "__main__":
    unittest.main()
