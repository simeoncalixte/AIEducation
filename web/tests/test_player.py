"""Tests for the student web player (SCRUM-126, SCRUM-20)."""

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


class PlayerTestCase(unittest.TestCase):
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

    def _login(self, user_id):
        with self.client.session_transaction() as sess:
            sess["actor_id"] = user_id

    def _publish_challenge_lesson(self):
        for kind, vid in (
                ("asset", self.ids["asset_draft_id"]),
                ("asset", self.ids["challenge_draft_id"]),
                ("stage", self.ids["stage_draft_id"]),
                ("lesson", self.ids["lesson_draft_id"])):
            self.client.post(f"/review/{kind}/{vid}/approve",
                             data={"rationale": "ok"})
            resp = self.client.post(f"/review/{kind}/{vid}/publish",
                                    data={"rationale": "ship"})
            self.assertEqual(resp.status_code, 302)

    def _assign(self):
        resp = self.client.post("/assignments", data={
            "lesson_id": str(self.ids["lesson_id"]),
            "classroom_id": str(self.room_id), "student_id": ""})
        self.assertEqual(resp.status_code, 302)
        return int(resp.headers["Location"].rsplit("/", 1)[-1])

    def test_home_lists_current_and_past_work(self):
        self._login(self.ids["student_id"])
        body = self.client.get("/home").get_data(as_text=True)
        self.assertIn("No assignments yet.", body)
        self._login(self.ids["teacher_id"])
        self._publish_challenge_lesson()
        aid = self._assign()
        self._login(self.ids["student_id"])
        body = self.client.get("/home").get_data(as_text=True)
        self.assertIn("Volcanoes", body)
        self.assertIn("not started", body)
        self.assertIn(f"/play/{aid}", body)

    def test_briefing_shows_lesson_shape(self):
        self._login(self.ids["teacher_id"])
        self._publish_challenge_lesson()
        aid = self._assign()
        self._login(self.ids["student_id"])
        body = self.client.get(f"/play/{aid}").get_data(as_text=True)
        for marker in ("Volcanoes", "sci.eruptions",
                       "Eruptions move magma", "Eruption", "Start lesson"):
            self.assertIn(marker, body)

    def test_full_play_flow_end_to_end(self):
        self._login(self.ids["teacher_id"])
        self._publish_challenge_lesson()
        aid = self._assign()
        self._login(self.ids["student_id"])
        resp = self.client.post(f"/play/{aid}/start")
        first = resp.headers["Location"]
        self.assertIn("/challenge/1", first)
        body = self.client.get(first).get_data(as_text=True)
        for marker in ("Challenge 1 of 1", "Label the Parts",
                       "crater", "vent"):
            self.assertIn(marker, body)
        resp = self.client.post(first, data={"goals": ["crater"]})
        self.assertIn("/debrief", resp.headers["Location"])
        body = self.client.get(resp.headers["Location"]).get_data(
            as_text=True)
        self.assertIn("crater", body)
        self.assertIn("pass", body)
        self.assertIn("vent", body)
        self.assertIn("fail", body)
        body = self.client.post(
            resp.headers["Location"].replace("/debrief", "/rate"),
            data={"score": "5"}, follow_redirects=True).get_data(
                as_text=True)
        self.assertIn("Rating recorded.", body)
        attempt_base = resp.headers["Location"].rsplit("/debrief", 1)[0]
        body = self.client.post(
            f"{attempt_base}/finish",
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("Attempt finished.", body)
        self.assertIn("Finished", body)
        resp = self.client.post(f"{attempt_base}/retry")
        retry_first = resp.headers["Location"]
        self.assertIn("/challenge/1", retry_first)
        self.assertNotEqual(retry_first, first)
        resp = self.client.post(
            retry_first, data={"goals": ["crater", "vent"]})
        body = self.client.get(resp.headers["Location"]).get_data(
            as_text=True)
        self.assertEqual(body.count("pass</span>"), 2)

    def test_teacher_cannot_start_attempt(self):
        self._publish_challenge_lesson()
        aid = self._assign()
        body = self.client.post(
            f"/play/{aid}/start",
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("forbidden", body)

    def test_attempt_isolation_between_students(self):
        self._login(self.ids["teacher_id"])
        self._publish_challenge_lesson()
        aid = self._assign()
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        with factory() as session, session.begin():
            second = m.AppUser(role=m.UserRole.student,
                               display_name="Sam2", login_ref="sam2")
            session.add(second)
            session.flush()
            session.add(m.Membership(
                user_id=second.id, classroom_id=self.room_id,
                status=m.MembershipStatus.active))
            second_id = second.id
        engine.dispose()
        self._login(second_id)
        other_first = self.client.post(
            f"/play/{aid}/start").headers["Location"]
        self._login(self.ids["student_id"])
        self.assertEqual(
            self.client.get(other_first).status_code, 403)
        self.assertEqual(
            self.client.post(other_first,
                             data={"goals": ["crater"]}).status_code, 403)

    def test_teacher_can_preview_attempt(self):
        self._login(self.ids["teacher_id"])
        self._publish_challenge_lesson()
        aid = self._assign()
        self._login(self.ids["student_id"])
        first = self.client.post(f"/play/{aid}/start").headers["Location"]
        self._login(self.ids["teacher_id"])
        self.assertEqual(self.client.get(first).status_code, 200)

    def test_unpublished_lesson_has_no_play(self):
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        with factory() as session, session.begin():
            school_id = session.scalar(select(m.School.id))
            lesson = m.Lesson(school_id=school_id,
                              classroom_id=self.room_id,
                              subject="math", title="Fractions")
            session.add(lesson)
            session.flush()
            lesson_id = lesson.id
        engine.dispose()
        resp = self.client.post("/assignments", data={
            "lesson_id": str(lesson_id),
            "classroom_id": str(self.room_id), "student_id": ""})
        aid = int(resp.headers["Location"].rsplit("/", 1)[-1])
        self._login(self.ids["student_id"])
        body = self.client.get(f"/play/{aid}").get_data(as_text=True)
        self.assertIn("not published yet", body)
        body = self.client.post(
            f"/play/{aid}/start",
            follow_redirects=True).get_data(as_text=True)
        self.assertIn("invalid_play", body)

    def test_invalid_challenge_index_is_404(self):
        self._login(self.ids["teacher_id"])
        self._publish_challenge_lesson()
        aid = self._assign()
        self._login(self.ids["student_id"])
        first = self.client.post(f"/play/{aid}/start").headers["Location"]
        attempt_base = first.rsplit("/challenge/1", 1)[0]
        self.assertEqual(
            self.client.get(f"{attempt_base}/challenge/9").status_code,
            404)


if __name__ == "__main__":
    unittest.main()
