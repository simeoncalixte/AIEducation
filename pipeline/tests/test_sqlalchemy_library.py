"""SQLAlchemy adapters against scratch SQLite (fast, hermetic)."""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "database"))

import DataModels as db
from evolvingclass_pipeline.adapters.sqlalchemy_library import (
    SqlAlchemyAssetLibrary,
    SqlAlchemyRunStore,
)
from evolvingclass_pipeline.domain import (
    AssetKind,
    GeneratedContent,
    Tag,
)


class AdapterCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        engine = db.get_engine(f"sqlite:///{cls.db_path}")
        db.Base.metadata.create_all(engine)
        cls.sessions = db.get_session_factory(f"sqlite:///{cls.db_path}")
        s = cls.sessions()
        user = db.AppUser(role=db.UserRole.teacher, display_name="T",
                          login_ref="t@t.t")
        s.add(user)
        s.commit()
        cls.user_id = user.id
        s.close()

    @classmethod
    def tearDownClass(cls):
        os.remove(cls.db_path)

    def test_run_lifecycle(self):
        runs = SqlAlchemyRunStore(self.sessions)
        run_id = runs.begin_run("a/v1", "m/v1", "p/v1", {"k": "v"}, "policy/v1")
        runs.mark_running(run_id)
        runs.mark_failed(run_id, "boom")
        s = self.sessions()
        run = s.get(db.GenerationRun, run_id)
        self.assertEqual(run.status, db.GenerationStatus.failed)
        self.assertEqual(run.attempts, 1)
        self.assertEqual(run.last_error, "boom")
        s.close()
        runs.mark_running(run_id)
        runs.mark_completed(run_id)
        s = self.sessions()
        self.assertEqual(
            s.get(db.GenerationRun, run_id).status,
            db.GenerationStatus.completed)
        s.close()

    def test_save_draft_round_trip(self):
        lib = SqlAlchemyAssetLibrary(self.sessions)
        runs = SqlAlchemyRunStore(self.sessions)
        run_id = runs.begin_run("a", "m", "p", {}, "policy/v1")
        ref = lib.save_draft(
            GeneratedContent(
                kind=AssetKind.text, title="Gravity",
                body={"text": "falling"}, tags=(Tag("subject", "physics"),),
                objective_refs=("falling bodies",), rationale="r"),
            "sha256:abc.json", {"directives": []}, run_id, self.user_id)
        s = self.sessions()
        version = s.get(db.AssetVersion, ref.version_id)
        self.assertEqual(version.status, db.VersionStatus.draft)
        self.assertEqual(version.content_ref, "sha256:abc.json")
        self.assertEqual(version.directive_snapshot, {"directives": []})
        self.assertEqual(version.generation_run_id, run_id)
        self.assertEqual(
            [(t.taxonomy, t.value) for t in version.tags],
            [(db.TagTaxonomy.subject, "physics")])
        self.assertEqual(list(version.objective_refs), ["falling bodies"])
        self.assertEqual(version.rationale, "r")
        s.close()

    def test_find_candidates_published_only_best_first(self):
        lib = SqlAlchemyAssetLibrary(self.sessions)
        runs = SqlAlchemyRunStore(self.sessions)
        run_id = runs.begin_run("a", "m", "p", {}, "policy/v1")
        base = dict(content_ref="sha256:x.json", snapshot={},
                    run_id=run_id, created_by_id=self.user_id)
        near = lib.save_draft(
            GeneratedContent(
                kind=AssetKind.text, title="Near", body={}, tags=(),
                objective_refs=("falling bodies",), rationale="r"), **base)
        far = lib.save_draft(
            GeneratedContent(
                kind=AssetKind.text, title="Far", body={}, tags=(),
                objective_refs=("unrelated",), rationale="r"), **base)
        s = self.sessions()
        s.get(db.AssetVersion, near.version_id).status = (
            db.VersionStatus.published)
        s.get(db.AssetVersion, far.version_id).status = db.VersionStatus.published
        draft = lib.save_draft(
            GeneratedContent(
                kind=AssetKind.text, title="Draft", body={}, tags=(),
                objective_refs=("falling bodies",), rationale="r"), **base)
        s.commit()
        s.close()
        matches = lib.find_candidates(AssetKind.text, (), ("falling bodies",))
        ids = [m.version_id for m in matches]
        self.assertIn(near.version_id, ids)
        self.assertIn(far.version_id, ids)
        self.assertNotIn(draft.version_id, ids)
        self.assertEqual(matches[0].version_id, near.version_id)
        self.assertGreater(matches[0].score, matches[1].score)

    def test_record_preview_pins_artifact_to_version(self):
        lib = SqlAlchemyAssetLibrary(self.sessions)
        runs = SqlAlchemyRunStore(self.sessions)
        run_id = runs.begin_run("a", "m", "p", {}, "policy/v1")
        ref = lib.save_draft(
            GeneratedContent(
                kind=AssetKind.text, title="Poster", body={}, tags=(),
                objective_refs=(), rationale="r"),
            content_ref="sha256:x.json", snapshot={}, run_id=run_id,
            created_by_id=self.user_id)
        lib.record_preview(ref.version_id, "poster", "7/v1_poster.svg")
        s = self.sessions()
        rows = s.query(db.PreviewArtifact).filter_by(
            asset_version_id=ref.version_id).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, db.PreviewKind.poster)
        self.assertEqual(rows[0].storage_ref, "7/v1_poster.svg")
        self.assertIsNotNone(rows[0].rendered_at)
        s.close()


if __name__ == "__main__":
    unittest.main()
