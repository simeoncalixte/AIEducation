"""Tests for the publication transaction (SCRUM-16, part 1)."""

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
    Approval,
    Asset,
    AssetKind,
    AssetUse,
    AssetVersion,
    Base,
    Classroom,
    Decision,
    Goal,
    GoalEvaluation,
    Lesson,
    LessonVersion,
    LessonVersionStage,
    Membership,
    MembershipStatus,
    PublishAction,
    PublishEvent,
    School,
    Stage,
    StageVersion,
    UserRole,
    VersionStatus,
)
from evolvingclass_service import (  # noqa: E402
    PublicationError,
    ensure_draft,
    publish_asset_version,
    publish_lesson_version,
    publish_stage_version,
    resolve_current_lesson_version,
    retire_lesson_version,
    rollback_lesson_version,
)


class PublicationTestCase(unittest.TestCase):
    def setUp(self):
        url = os.environ.get("EVOLVECLASS_TEST_DATABASE_URL")
        if url:
            engine = create_engine(url)
            Base.metadata.drop_all(engine)
        else:
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
            admin = AppUser(role=UserRole.admin, display_name="A",
                            login_ref="admin-1")
            student = AppUser(role=UserRole.student, display_name="S",
                              login_ref="student-1")
            outsider = AppUser(role=UserRole.teacher, display_name="O",
                               login_ref="teacher-2")
            session.add_all([teacher, admin, student, outsider])
            session.flush()
            session.add_all([
                Membership(user_id=teacher.id, classroom_id=room.id,
                           status=MembershipStatus.active),
                Membership(user_id=admin.id, school_id=school.id,
                           status=MembershipStatus.active),
                Membership(user_id=outsider.id, school_id=other.id,
                           status=MembershipStatus.active),
            ])
            self.school_id = school.id
            self.room_id = room.id
            self.teacher_id = teacher.id
            self.admin_id = admin.id
            self.student_id = student.id
            self.outsider_id = outsider.id

    # -- fixtures ------------------------------------------------------

    def _lesson(self, session):
        lesson = Lesson(school_id=self.school_id, classroom_id=self.room_id,
                        subject="science", title="L")
        session.add(lesson)
        session.flush()
        return lesson

    def _asset_version(self, session, kind=AssetKind.prop, school=True):
        asset = Asset(kind=kind, title="A", created_by_id=self.teacher_id,
                      school_id=self.school_id if school else None)
        session.add(asset)
        session.flush()
        version = AssetVersion(asset_id=asset.id, version_no=1,
                               status=VersionStatus.draft, rationale="r",
                               objective_refs=[], content_ref="c",
                               param_schema={})
        session.add(version)
        session.flush()
        return version

    def _stage_version(self, session, lesson):
        stage = Stage(lesson_id=lesson.id, position=1, title="S")
        session.add(stage)
        session.flush()
        version = StageVersion(stage_id=stage.id, version_no=1,
                               status=VersionStatus.draft, rationale="r")
        session.add(version)
        session.flush()
        return version

    def _lesson_version(self, session, lesson, no=1, student=None):
        version = LessonVersion(
            lesson_id=lesson.id, version_no=no, status=VersionStatus.draft,
            rationale="r", objective_refs=[], student_scope_id=student)
        session.add(version)
        session.flush()
        return version

    def _approve(self, session, kind, version_id):
        session.add(Approval(**{f"{kind}_version_id": version_id},
                             actor_id=self.teacher_id,
                             decision=Decision.approved, rationale="ok"))

    def _full_graph(self):
        """Draft asset + stage + lesson with uses, composition, approvals."""
        with self.make_session() as session, session.begin():
            lesson = self._lesson(session)
            asset_v = self._asset_version(session)
            stage_v = self._stage_version(session, lesson)
            session.add(AssetUse(asset_version_id=asset_v.id,
                                 stage_version_id=stage_v.id,
                                 position=1, role="prop",
                                 param_overrides={}))
            lesson_v = self._lesson_version(session, lesson)
            session.add(LessonVersionStage(lesson_version_id=lesson_v.id,
                                           stage_version_id=stage_v.id,
                                           position=1))
            self._approve(session, "asset", asset_v.id)
            self._approve(session, "stage", stage_v.id)
            self._approve(session, "lesson", lesson_v.id)
            return lesson_v.id, stage_v.id, asset_v.id

    def _status(self, model, version_id):
        with self.make_session() as session:
            return session.get(model, version_id).status

    def _events(self, kind, version_id):
        with self.make_session() as session:
            return list(session.scalars(
                select(PublishEvent)
                .where(getattr(PublishEvent, f"{kind}_version_id") == version_id)
                .order_by(PublishEvent.id)
            ))

    # -- publish --------------------------------------------------------

    def test_publish_lesson_happy_path_flips_and_audits(self):
        lesson_v, stage_v, asset_v = self._full_graph()
        ra = publish_asset_version(self.make_session, asset_v,
                                   self.teacher_id, "go")
        rs = publish_stage_version(self.make_session, stage_v,
                                   self.teacher_id, "go")
        rl = publish_lesson_version(self.make_session, lesson_v,
                                    self.teacher_id, "go")
        self.assertEqual(ra.status, "published")
        self.assertEqual(rs.status, "published")
        self.assertEqual(rl.status, "published")
        self.assertEqual(self._status(LessonVersion, lesson_v),
                         VersionStatus.published)
        with self.make_session() as session:
            self.assertIsNotNone(
                session.get(LessonVersion, lesson_v).published_at)
        events = self._events("lesson", lesson_v)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].action, PublishAction.published)
        self.assertEqual(events[0].actor_id, self.teacher_id)

    def test_publish_rejects_without_approval(self):
        lesson_v, _, _ = self._full_graph()
        with self.make_session() as session, session.begin():
            session.query(Approval).filter(
                Approval.lesson_version_id == lesson_v).delete()
        with self.assertRaises(PublicationError) as ctx:
            publish_lesson_version(self.make_session, lesson_v,
                                   self.teacher_id, "go")
        self.assertEqual(ctx.exception.code, "not_approved")
        self.assertEqual(self._status(LessonVersion, lesson_v),
                         VersionStatus.draft)

    def test_publish_rejects_when_latest_decision_is_rejection(self):
        lesson_v, _, _ = self._full_graph()
        with self.make_session() as session, session.begin():
            session.add(Approval(lesson_version_id=lesson_v,
                                 actor_id=self.teacher_id,
                                 decision=Decision.rejected,
                                 rationale="no"))
        with self.assertRaises(PublicationError) as ctx:
            publish_lesson_version(self.make_session, lesson_v,
                                   self.teacher_id, "go")
        self.assertEqual(ctx.exception.code, "not_approved")

    def test_publish_lesson_rejects_draft_stage(self):
        lesson_v, _, _ = self._full_graph()
        with self.assertRaises(PublicationError) as ctx:
            publish_lesson_version(self.make_session, lesson_v,
                                   self.teacher_id, "go")
        self.assertEqual(ctx.exception.code, "unpublished_dependency")

    def test_publish_lesson_rejects_empty_composition(self):
        with self.make_session() as session, session.begin():
            lesson = self._lesson(session)
            lesson_v = self._lesson_version(session, lesson)
            self._approve(session, "lesson", lesson_v.id)
            vid = lesson_v.id
        with self.assertRaises(PublicationError) as ctx:
            publish_lesson_version(self.make_session, vid,
                                   self.teacher_id, "go")
        self.assertEqual(ctx.exception.code, "empty_composition")

    def test_publish_stage_rejects_draft_asset(self):
        _, stage_v, _ = self._full_graph()
        with self.assertRaises(PublicationError) as ctx:
            publish_stage_version(self.make_session, stage_v,
                                  self.teacher_id, "go")
        self.assertEqual(ctx.exception.code, "unpublished_dependency")

    def test_publish_challenge_requires_goals_then_succeeds(self):
        with self.make_session() as session, session.begin():
            version = self._asset_version(session, kind=AssetKind.challenge)
            self._approve(session, "asset", version.id)
            vid = version.id
        with self.assertRaises(PublicationError) as ctx:
            publish_asset_version(self.make_session, vid,
                                  self.teacher_id, "go")
        self.assertEqual(ctx.exception.code, "missing_goals")
        with self.make_session() as session, session.begin():
            session.add(Goal(challenge_version_id=vid, key="g1", rule={},
                             evaluation=GoalEvaluation.deterministic,
                             template_ref="t"))
        result = publish_asset_version(self.make_session, vid,
                                       self.teacher_id, "go")
        self.assertEqual(result.status, "published")

    def test_republish_published_rejected(self):
        lesson_v, stage_v, asset_v = self._full_graph()
        publish_asset_version(self.make_session, asset_v, self.teacher_id, "go")
        with self.assertRaises(PublicationError) as ctx:
            publish_asset_version(self.make_session, asset_v,
                                  self.teacher_id, "again")
        self.assertEqual(ctx.exception.code, "not_draft")
        self.assertEqual(self._events("asset", asset_v)[0].action,
                         PublishAction.published)

    # -- authorization ---------------------------------------------------

    def test_student_cannot_publish(self):
        lesson_v, stage_v, asset_v = self._full_graph()
        with self.assertRaises(PublicationError) as ctx:
            publish_asset_version(self.make_session, asset_v,
                                  self.student_id, "go")
        self.assertEqual(ctx.exception.code, "forbidden")

    def test_outsider_teacher_cannot_publish(self):
        lesson_v, stage_v, asset_v = self._full_graph()
        with self.assertRaises(PublicationError) as ctx:
            publish_asset_version(self.make_session, asset_v,
                                  self.outsider_id, "go")
        self.assertEqual(ctx.exception.code, "forbidden")

    def test_global_asset_requires_admin(self):
        with self.make_session() as session, session.begin():
            version = self._asset_version(session, school=False)
            self._approve(session, "asset", version.id)
            vid = version.id
        with self.assertRaises(PublicationError) as ctx:
            publish_asset_version(self.make_session, vid,
                                  self.teacher_id, "go")
        self.assertEqual(ctx.exception.code, "forbidden")
        result = publish_asset_version(self.make_session, vid,
                                       self.admin_id, "go")
        self.assertEqual(result.status, "published")

    # -- rollback and retire ---------------------------------------------

    def _two_live_lessons(self):
        lesson_v, stage_v, asset_v = self._full_graph()
        publish_asset_version(self.make_session, asset_v, self.teacher_id, "go")
        publish_stage_version(self.make_session, stage_v, self.teacher_id, "go")
        publish_lesson_version(self.make_session, lesson_v, self.teacher_id, "go")
        with self.make_session() as session, session.begin():
            lesson_id = session.get(LessonVersion, lesson_v).lesson_id
            lesson = session.get(Lesson, lesson_id)
            v2 = self._lesson_version(session, lesson, no=2)
            session.add(LessonVersionStage(lesson_version_id=v2.id,
                                           stage_version_id=stage_v,
                                           position=1))
            self._approve(session, "lesson", v2.id)
            v2_id = v2.id
        publish_lesson_version(self.make_session, v2_id, self.teacher_id, "go")
        return lesson_v, v2_id

    def test_rollback_restores_prior_and_demotes_current(self):
        v1, v2 = self._two_live_lessons()
        retire_lesson_version(self.make_session, v1, self.teacher_id, "old")
        result = rollback_lesson_version(self.make_session, v1,
                                         self.teacher_id, "v2 broken")
        self.assertEqual(result.status, "published")
        self.assertEqual(len(result.event_ids), 2)
        self.assertEqual(self._status(LessonVersion, v1),
                         VersionStatus.published)
        self.assertEqual(self._status(LessonVersion, v2),
                         VersionStatus.retired)
        actions = [e.action for e in self._events("lesson", v1)]
        self.assertEqual(actions, [PublishAction.published,
                                   PublishAction.retired,
                                   PublishAction.rolled_back])

    def test_rollback_without_live_rejected(self):
        v1, v2 = self._two_live_lessons()
        retire_lesson_version(self.make_session, v1, self.teacher_id, "old")
        retire_lesson_version(self.make_session, v2, self.teacher_id, "old")
        with self.assertRaises(PublicationError) as ctx:
            rollback_lesson_version(self.make_session, v1,
                                    self.teacher_id, "back")
        self.assertEqual(ctx.exception.code, "nothing_live")

    def test_retire_flips_and_rejects_draft(self):
        lesson_v, stage_v, asset_v = self._full_graph()
        with self.assertRaises(PublicationError) as ctx:
            retire_lesson_version(self.make_session, lesson_v,
                                  self.teacher_id, "no")
        self.assertEqual(ctx.exception.code, "not_published")
        publish_asset_version(self.make_session, asset_v, self.teacher_id, "go")
        publish_stage_version(self.make_session, stage_v, self.teacher_id, "go")
        publish_lesson_version(self.make_session, lesson_v, self.teacher_id, "go")
        result = retire_lesson_version(self.make_session, lesson_v,
                                       self.teacher_id, "done")
        self.assertEqual(result.status, "retired")
        self.assertEqual(self._status(LessonVersion, lesson_v),
                         VersionStatus.retired)

    # -- resolution and freeze guard --------------------------------------

    def test_resolve_prefers_personal_over_default(self):
        lesson_v, stage_v, asset_v = self._full_graph()
        publish_asset_version(self.make_session, asset_v, self.teacher_id, "go")
        publish_stage_version(self.make_session, stage_v, self.teacher_id, "go")
        publish_lesson_version(self.make_session, lesson_v, self.teacher_id, "go")
        with self.make_session() as session, session.begin():
            lesson_id = session.get(LessonVersion, lesson_v).lesson_id
            lesson = session.get(Lesson, lesson_id)
            personal = self._lesson_version(session, lesson, no=2,
                                            student=self.student_id)
            session.add(LessonVersionStage(lesson_version_id=personal.id,
                                           stage_version_id=stage_v,
                                           position=1))
            self._approve(session, "lesson", personal.id)
            personal_id = personal.id
        publish_lesson_version(self.make_session, personal_id,
                               self.teacher_id, "go")
        with self.make_session() as session:
            got = resolve_current_lesson_version(session, lesson_id,
                                                 self.student_id)
            self.assertEqual(got.id, personal_id)
            other = AppUser(role=UserRole.student, display_name="S2",
                            login_ref="student-2")
            session.add(other)
            session.flush()
            fallback = resolve_current_lesson_version(session, lesson_id,
                                                      other.id)
            self.assertEqual(fallback.id, lesson_v)
            self.assertIsNone(
                resolve_current_lesson_version(session, lesson_id + 999,
                                               self.student_id))

    def test_ensure_draft(self):
        lesson_v, stage_v, asset_v = self._full_graph()
        with self.make_session() as session:
            ensure_draft(session.get(LessonVersion, lesson_v))
        publish_asset_version(self.make_session, asset_v, self.teacher_id, "go")
        publish_stage_version(self.make_session, stage_v, self.teacher_id, "go")
        publish_lesson_version(self.make_session, lesson_v, self.teacher_id, "go")
        with self.make_session() as session:
            with self.assertRaises(PublicationError) as ctx:
                ensure_draft(session.get(LessonVersion, lesson_v))
            self.assertEqual(ctx.exception.code, "not_draft")


if __name__ == "__main__":
    unittest.main()
