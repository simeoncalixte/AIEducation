"""Tests for assignment and progress views (SCRUM-125, SCRUM-18)."""

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


class AssignmentViewTestCase(unittest.TestCase):
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
        with factory() as session:
            self.room_id = session.scalar(select(m.Classroom.id))
        engine.dispose()

    def tearDown(self):
        os.unlink(self._tmp)

    def _assign(self, **overrides):
        data = {"lesson_id": str(self.ids["lesson_id"]),
                "classroom_id": str(self.room_id), "student_id": ""}
        data.update(overrides)
        return self.client.post("/assignments", data=data,
                               follow_redirects=True)

    def _add_play(self, assignment_id):
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        with factory() as session, session.begin():
            lesson_v = session.scalar(
                select(m.LessonVersion)
                .where(m.LessonVersion.status == m.VersionStatus.published)
                .order_by(m.LessonVersion.id))
            goal_id = session.scalar(select(m.Goal.id))
            attempt = m.Attempt(
                assignment_id=assignment_id,
                student_id=self.ids["student_id"],
                pinned_lesson_version_id=lesson_v.id)
            session.add(attempt)
            session.flush()
            session.add(m.ExperienceEvent(
                attempt_id=attempt.id, client_event_id="v1",
                sequence_no=1, origin=m.EventOrigin.server,
                actor_id=self.ids["teacher_id"], verb="goal-verdict",
                object_type="goal", object_ref="crater", goal_id=goal_id,
                payload={"passed": False}))
            session.add(m.Rating(
                lesson_version_id=lesson_v.id,
                author_id=self.ids["student_id"], score=4))
            attempt_id = attempt.id
            verdict_id = session.scalar(
                select(m.ExperienceEvent.id)
                .where(m.ExperienceEvent.attempt_id == attempt.id,
                       m.ExperienceEvent.verb == "goal-verdict"))
        engine.dispose()
        return attempt_id, verdict_id

    def test_list_shows_empty_state_and_form(self):
        body = self.client.get("/assignments").get_data(as_text=True)
        for marker in ("No assignments yet.", "Volcanoes", "Room 1",
                       "Sam", "Assign lesson"):
            self.assertIn(marker, body)

    def test_unknown_assignment_is_404(self):
        self.assertEqual(
            self.client.get("/assignments/9999").status_code, 404)

    def test_assign_to_classroom_and_student(self):
        body = self._assign().get_data(as_text=True)
        self.assertIn("Assignment recorded.", body)
        self.assertIn("Volcanoes", body)
        self.assertIn("Room 1", body)
        self.assertIn("Sam", body)
        self.assertIn("No attempts yet.", body)
        body = self._assign(
            classroom_id="",
            student_id=str(self.ids["student_id"])).get_data(as_text=True)
        self.assertIn("Assignment recorded.", body)

    def test_assign_requires_exactly_one_target(self):
        body = self._assign(classroom_id="", student_id="").get_data(
            as_text=True)
        self.assertIn("invalid_scope", body)
        body = self._assign(
            student_id=str(self.ids["student_id"])).get_data(as_text=True)
        self.assertIn("invalid_scope", body)

    def test_progress_shows_verdicts_rating_and_flags(self):
        self._assign()
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        with factory() as session:
            aid = session.scalar(select(m.Assignment.id))
        engine.dispose()
        attempt_id, verdict_id = self._add_play(aid)
        body = self.client.get(f"/assignments/{aid}").get_data(as_text=True)
        for marker in ("crater", "fail", "4", "Override",
                       "Flag misconception", "No flags on this attempt."):
            self.assertIn(marker, body)
        body = self.client.post(
            f"/verdicts/{verdict_id}/override",
            data={"reason": "Reread.", "corrected": "pass",
                  "next": f"/assignments/{aid}"},
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("Override recorded.", body)
        self.assertIn("overridden: Reread.", body)
        body = self.client.post(
            f"/attempts/{attempt_id}/flag",
            data={"note": "Said lava.", "next": f"/assignments/{aid}"},
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("Flag recorded.", body)
        self.assertIn("Said lava.", body)

    def test_student_cannot_open_assignments(self):
        with self.client.session_transaction() as sess:
            sess["actor_id"] = self.ids["student_id"]
        self.assertEqual(self.client.get("/assignments").status_code, 403)


if __name__ == "__main__":
    unittest.main()
