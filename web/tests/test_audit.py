"""Tests for the admin audit views (SCRUM-21)."""

import datetime as _dt
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


class AuditTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self._tmp = tmp.name
        self.url = f"sqlite:///{tmp.name}"
        self.ids = seed(self.url)
        self.app = create_app(self.url)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.client.post("/login", data={"login_ref": "ash"})

    def tearDown(self):
        os.unlink(self._tmp)

    def test_audit_shows_status_and_trail(self):
        body = self.client.get("/audit").get_data(as_text=True)
        for marker in ("Room 1", "Volcanoes", "Drafts", "Published",
                       "Tess", "approved", "published",
                       "asset Volcano Model v1"):
            self.assertIn(marker, body)

    def test_second_classroom_appears(self):
        engine = create_engine(self.url)
        factory = sessionmaker(bind=engine)
        with factory() as session, session.begin():
            school_id = session.scalar(select(m.School.id))
            room = m.Classroom(school_id=school_id, name="Room 2")
            session.add(room)
            session.flush()
            session.add(m.Lesson(school_id=school_id,
                                 classroom_id=room.id, subject="math",
                                 title="Fractions"))
        engine.dispose()
        body = self.client.get("/audit").get_data(as_text=True)
        self.assertIn("Room 2", body)
        self.assertIn("Fractions", body)

    def test_actor_filter(self):
        teacher = self.client.get(
            f"/audit?actor={self.ids['teacher_id']}").get_data(as_text=True)
        self.assertIn("Tess", teacher)
        self.assertIn("approved", teacher)
        student = self.client.get(
            f"/audit?actor={self.ids['student_id']}").get_data(as_text=True)
        self.assertIn("No history matches", student)

    def test_date_filters(self):
        today = _dt.date.today()
        tomorrow = today + _dt.timedelta(days=1)
        yesterday = today - _dt.timedelta(days=1)
        body = self.client.get(f"/audit?since={today}").get_data(
            as_text=True)
        self.assertIn("approved", body)
        body = self.client.get(f"/audit?since={tomorrow}").get_data(
            as_text=True)
        self.assertIn("No history matches", body)
        body = self.client.get(f"/audit?until={yesterday}").get_data(
            as_text=True)
        self.assertIn("No history matches", body)
        body = self.client.get("/audit?since=not-a-date").get_data(
            as_text=True)
        self.assertIn("approved", body)

    def test_audit_is_admin_only(self):
        with self.client.session_transaction() as sess:
            sess["actor_id"] = self.ids["teacher_id"]
        resp = self.client.get("/audit")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("school admins", resp.get_data(as_text=True))
        with self.client.session_transaction() as sess:
            sess["actor_id"] = self.ids["student_id"]
        self.assertEqual(self.client.get("/audit").status_code, 403)
        with self.client.session_transaction() as sess:
            sess.pop("actor_id", None)
        resp = self.client.get("/audit")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])


if __name__ == "__main__":
    unittest.main()
