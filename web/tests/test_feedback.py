"""Tests for verdict overrides and misconception flags (SCRUM-19)."""

import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "database"))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "service"))
sys.path.insert(0, os.path.join(ROOT, "web"))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import DataModels as m  # noqa: E402
from evolvingclass_web.app import create_app  # noqa: E402
from evolvingclass_web.seed import seed  # noqa: E402


class FeedbackRouteTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self._tmp = tmp.name
        self.url = f"sqlite:///{tmp.name}"
        self.ids = seed(self.url)
        self.app = create_app(self.url)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["actor_id"] = self.ids["teacher_id"]
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        with factory() as session, session.begin():
            room_id = session.scalar(select(m.Classroom.id))
            lesson_v = session.scalar(
                select(m.LessonVersion)
                .where(m.LessonVersion.status == m.VersionStatus.published)
                .order_by(m.LessonVersion.id))
            goal_id = session.scalar(select(m.Goal.id))
            misc_id = session.scalar(select(m.Misconception.id))
            assignment = m.Assignment(
                lesson_id=lesson_v.lesson_id, classroom_id=room_id,
                assigned_by_id=self.ids["teacher_id"])
            session.add(assignment)
            session.flush()
            attempt = m.Attempt(
                assignment_id=assignment.id,
                student_id=self.ids["student_id"],
                pinned_lesson_version_id=lesson_v.id)
            session.add(attempt)
            session.flush()
            verdict = m.ExperienceEvent(
                attempt_id=attempt.id, client_event_id="v1",
                sequence_no=1, origin=m.EventOrigin.server,
                actor_id=self.ids["teacher_id"], verb="goal-verdict",
                object_type="goal", object_ref="crater", goal_id=goal_id,
                payload={"passed": False})
            session.add(verdict)
            session.flush()
            self.attempt_id = attempt.id
            self.verdict_id = verdict.id
            self.misc_id = misc_id
        engine.dispose()

    def tearDown(self):
        os.unlink(self._tmp)

    def _overrides(self):
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        try:
            with factory() as session:
                rows = list(session.scalars(
                    select(m.VerdictOverride).where(
                        m.VerdictOverride.verdict_event_id ==
                        self.verdict_id)))
                for row in rows:
                    session.expunge(row)
                return rows
        finally:
            engine.dispose()

    def _flags(self):
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        try:
            with factory() as session:
                rows = list(session.scalars(
                    select(m.ExperienceEvent).where(
                        m.ExperienceEvent.attempt_id == self.attempt_id,
                        m.ExperienceEvent.verb == "misconception-flagged",
                    )))
                for row in rows:
                    session.expunge(row)
                return rows
        finally:
            engine.dispose()

    def test_override_records_correction(self):
        body = self.client.post(
            f"/verdicts/{self.verdict_id}/override",
            data={"reason": "Reread it.", "corrected": "pass",
                  "score": "0.9", "next": "/home"},
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("Override recorded.", body)
        rows = self._overrides()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].reason, "Reread it.")
        self.assertTrue(rows[0].corrected_passed)
        self.assertEqual(rows[0].corrected_score, 0.9)

    def test_override_requires_reason(self):
        body = self.client.post(
            f"/verdicts/{self.verdict_id}/override",
            data={"reason": "  ", "corrected": "pass", "next": "/home"},
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("invalid_feedback", body)
        self.assertEqual(self._overrides(), [])

    def test_flag_records_misconception_event(self):
        body = self.client.post(
            f"/attempts/{self.attempt_id}/flag",
            data={"misconception_id": str(self.misc_id),
                  "note": "Said lava.", "next": "/home"},
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("Flag recorded.", body)
        rows = self._flags()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].object_ref, str(self.misc_id))
        self.assertEqual(rows[0].payload["note"], "Said lava.")

    def test_flag_requires_content(self):
        body = self.client.post(
            f"/attempts/{self.attempt_id}/flag",
            data={"note": "  ", "next": "/home"},
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("invalid_feedback", body)
        self.assertEqual(self._flags(), [])

    def test_student_cannot_give_feedback(self):
        with self.client.session_transaction() as sess:
            sess["actor_id"] = self.ids["student_id"]
        self.assertEqual(
            self.client.post(
                f"/verdicts/{self.verdict_id}/override",
                data={"reason": "x"}).status_code, 403)
        self.assertEqual(
            self.client.post(
                f"/attempts/{self.attempt_id}/flag",
                data={"note": "x"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
