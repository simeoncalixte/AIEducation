"""Schema guarantees from the review hardening pass.

Runs the real Alembic history against a scratch SQLite database, then asserts
the data contracts the APIs will rely on: composition pinning, publish audit,
override history, event replay rules, identity uniqueness, and CHECK bounds.

Run from database/:  python -m unittest discover tests
"""

import os
import tempfile
import unittest

from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

HERE = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.dirname(HERE)


def _upgrade_scratch(path):
    cfg = Config(os.path.join(DB_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(DB_DIR, "alembic"))
    os.environ["DATABASE_URL"] = f"sqlite:///{path}"
    command.upgrade(cfg, "head")


class SchemaGuarantees(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        _upgrade_scratch(cls.db_path)
        import sys

        sys.path.insert(0, DB_DIR)
        import DataModels as m

        cls.m = m
        cls.Session = m.get_session_factory(f"sqlite:///{cls.db_path}")
        s = cls.Session()
        school = m.School(name="T")
        s.add(school)
        s.flush()
        room = m.Classroom(school_id=school.id, name="R")
        teacher = m.AppUser(
            role=m.UserRole.teacher, display_name="T", login_ref="t@t.t"
        )
        student = m.AppUser(
            role=m.UserRole.student, display_name="S", login_ref="s@t.t"
        )
        s.add_all([room, teacher, student])
        s.flush()
        lesson = m.Lesson(
            school_id=school.id, classroom_id=room.id, subject="P", title="L"
        )
        s.add(lesson)
        s.flush()
        lv = m.LessonVersion(
            lesson_id=lesson.id, version_no=1,
            status=m.VersionStatus.published, rationale="r", objective_refs=[],
        )
        s.add(lv)
        s.flush()
        assign = m.Assignment(
            lesson_id=lesson.id, classroom_id=room.id, assigned_by_id=teacher.id
        )
        s.add(assign)
        s.flush()
        attempt = m.Attempt(
            assignment_id=assign.id, student_id=student.id,
            pinned_lesson_version_id=lv.id,
        )
        s.add(attempt)
        s.commit()
        cls.ids = {
            "school": school.id, "room": room.id, "teacher": teacher.id,
            "student": student.id, "lesson": lesson.id, "lv": lv.id,
            "assign": assign.id, "attempt": attempt.id,
        }
        s.close()

    @classmethod
    def tearDownClass(cls):
        os.remove(cls.db_path)

    def session(self):
        return self.Session()

    def test_all_tables_exist(self):
        self.assertEqual(len(self.m.Base.metadata.tables), 39)
        for t in ("lesson_version_stage", "publish_event", "goal_misconception"):
            self.assertIn(t, self.m.Base.metadata.tables)

    def test_composition_position_unique(self):
        m, ids = self.m, self.ids
        s = self.session()
        stage = m.Stage(lesson_id=ids["lesson"], position=1, title="S")
        s.add(stage)
        s.flush()
        sv = m.StageVersion(
            stage_id=stage.id, version_no=1,
            status=m.VersionStatus.published, rationale="r",
        )
        s.add(sv)
        s.flush()
        s.add(m.LessonVersionStage(
            lesson_version_id=ids["lv"], stage_version_id=sv.id, position=1,
        ))
        s.commit()
        s.add(m.LessonVersionStage(
            lesson_version_id=ids["lv"], stage_version_id=sv.id, position=1,
        ))
        with self.assertRaises(IntegrityError):
            s.commit()
        s.rollback()
        s.close()

    def test_override_history_keeps_correction(self):
        m, ids = self.m, self.ids
        s = self.session()
        ev = m.ExperienceEvent(
            attempt_id=ids["attempt"], client_event_id="v1", sequence_no=11,
            origin=m.EventOrigin.server, actor_id=ids["teacher"],
            verb="goal-verdict", object_type="goal", object_ref="g1", payload={},
        )
        s.add(ev)
        s.flush()
        s.add(m.VerdictOverride(
            verdict_event_id=ev.id, teacher_id=ids["teacher"],
            reason="reread", corrected_passed=True, corrected_score=0.8,
        ))
        s.commit()
        got = s.query(m.VerdictOverride).filter_by(verdict_event_id=ev.id).one()
        self.assertTrue(got.corrected_passed)
        self.assertEqual(got.corrected_score, 0.8)
        s.close()

    def test_event_idempotency_and_sequence_unique(self):
        m, ids = self.m, self.ids
        s = self.session()
        kw = dict(
            attempt_id=ids["attempt"], actor_id=ids["student"],
            origin=m.EventOrigin.client, verb="attempted",
            object_type="challenge", object_ref="c", payload={},
        )
        s.add(m.ExperienceEvent(client_event_id="dup", sequence_no=21, **kw))
        s.commit()
        s.add(m.ExperienceEvent(client_event_id="dup", sequence_no=22, **kw))
        with self.assertRaises(IntegrityError):
            s.commit()
        s.rollback()
        s.add(m.ExperienceEvent(client_event_id="other", sequence_no=21, **kw))
        with self.assertRaises(IntegrityError):
            s.commit()
        s.rollback()
        s.close()

    def test_client_cannot_emit_server_verbs(self):
        m, ids = self.m, self.ids
        s = self.session()
        s.add(m.ExperienceEvent(
            attempt_id=ids["attempt"], client_event_id="bad", sequence_no=31,
            origin=m.EventOrigin.client, actor_id=ids["student"],
            verb="goal-verdict", object_type="goal", object_ref="g", payload={},
        ))
        with self.assertRaises(IntegrityError):
            s.commit()
        s.rollback()
        s.close()

    def test_teacher_goal_requires_rubric(self):
        m = self.m
        s = self.session()
        teacher = s.query(m.AppUser).filter_by(login_ref="t@t.t").one()
        asset = m.Asset(kind=m.AssetKind.challenge, title="C",
                        created_by_id=teacher.id)
        s.add(asset)
        s.flush()
        av = m.AssetVersion(
            asset_id=asset.id, version_no=1, status=m.VersionStatus.draft,
            rationale="r", objective_refs=[], content_ref="c", param_schema={},
        )
        s.add(av)
        s.flush()
        s.add(m.Goal(challenge_version_id=av.id, key="k",
                     rule={}, evaluation=m.GoalEvaluation.teacher,
                     rubric=None, template_ref="t"))
        with self.assertRaises(IntegrityError):
            s.commit()
        s.rollback()
        s.close()

    def test_rating_bounds(self):
        m, ids = self.m, self.ids
        s = self.session()
        s.add(m.Rating(lesson_version_id=ids["lv"], author_id=ids["teacher"],
                       score=6))
        with self.assertRaises(IntegrityError):
            s.commit()
        s.rollback()
        s.close()

    def test_login_and_membership_unique(self):
        m, ids = self.m, self.ids
        s = self.session()
        s.add(m.AppUser(role=m.UserRole.student, display_name="X",
                        login_ref="s@t.t"))
        with self.assertRaises(IntegrityError):
            s.commit()
        s.rollback()
        s.add(m.Membership(user_id=ids["student"], classroom_id=ids["room"]))
        s.add(m.Membership(user_id=ids["student"], classroom_id=ids["room"]))
        with self.assertRaises(IntegrityError):
            s.commit()
        s.rollback()
        s.close()

    def test_consent_history_preserved(self):
        m, ids = self.m, self.ids
        s = self.session()
        for _ in range(2):
            s.add(m.ConsentRecord(
                student_id=ids["student"], consent_type="camera",
                policy_version="v1", source="test",
            ))
        s.commit()
        n = s.query(m.ConsentRecord).filter_by(
            student_id=ids["student"], consent_type="camera").count()
        self.assertEqual(n, 2)
        s.close()

    def test_retry_links_attempts(self):
        m, ids = self.m, self.ids
        s = self.session()
        retry = m.Attempt(
            assignment_id=ids["assign"], student_id=ids["student"],
            pinned_lesson_version_id=ids["lv"], retry_of_id=ids["attempt"],
        )
        s.add(retry)
        s.commit()
        parent = s.get(m.Attempt, ids["attempt"])
        self.assertEqual(len(parent.retries), 1)
        self.assertEqual(retry.retry_of.id, ids["attempt"])
        s.close()


if __name__ == "__main__":
    unittest.main()
