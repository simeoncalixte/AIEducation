"""End-to-end propose() against real adapters plus scratch SQLite.

SCRUM-26: agents build assets only on library miss. SCRUM-77 proves the
miss is recorded on the resulting proposal; SCRUM-78 proves the new
asset ships with tags, objective mapping, and rationale.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "database"))

import DataModels as db
from evolvingclass_pipeline.adapters.filesystem_content import (
    FilesystemContentStore,
)
from evolvingclass_pipeline.adapters.sqlalchemy_library import (
    SqlAlchemyAssetLibrary,
    SqlAlchemyRunStore,
)
from evolvingclass_pipeline.adapters.svg_preview import SvgPreviewRenderer
from evolvingclass_pipeline.agents.template_backend import TemplateAssetBackend
from evolvingclass_pipeline.asset_pipeline import AssetPipeline
from evolvingclass_pipeline.domain import (
    AssetKind,
    DirectiveInput,
    DirectiveKind,
    GeneratedContent,
    GenerationRequest,
    Tag,
)
from evolvingclass_pipeline.policy import ContentPolicy


class CountingBackend(TemplateAssetBackend):
    def __init__(self):
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        return super().generate(request)


class ProposeIntegrationCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        cls.url = f"sqlite:///{cls.db_path}"
        engine = db.get_engine(cls.url)
        db.Base.metadata.create_all(engine)
        cls.sessions = db.get_session_factory(cls.url)
        cls.content_root = tempfile.mkdtemp(prefix="ec-content-")
        cls.preview_root = tempfile.mkdtemp(prefix="ec-preview-")
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
        shutil.rmtree(cls.content_root, ignore_errors=True)
        shutil.rmtree(cls.preview_root, ignore_errors=True)

    def make_pipeline(self, backend=None):
        backend = backend or TemplateAssetBackend()
        pipe = AssetPipeline(
            SqlAlchemyAssetLibrary(self.sessions),
            backend,
            SvgPreviewRenderer(self.preview_root),
            SqlAlchemyRunStore(self.sessions),
            FilesystemContentStore(self.content_root),
            policy=ContentPolicy(),
        )
        return pipe, backend

    def test_miss_records_note_and_ships_tags_objectives_rationale(self):
        # SCRUM-77 + SCRUM-78 on the real stack: empty library, so a miss.
        pipe, _ = self.make_pipeline()
        request = GenerationRequest(
            kind=AssetKind.text,
            title="Gravity",
            objectives=("falling bodies",),
            tags=(Tag("subject", "physics"), Tag("age_band", "10-12")),
            directives=(DirectiveInput(
                id=11, kind=DirectiveKind.brief, focus="intro",
                constraints={}, priority=1),),
            parameters={},
        )
        result = pipe.propose(request, created_by_id=self.user_id)
        self.assertFalse(result.reused)

        s = self.sessions()
        try:
            version = s.get(db.AssetVersion, result.version_id)
            self.assertEqual(version.status, db.VersionStatus.draft)
            # SCRUM-77: the miss is noted on the proposal itself.
            self.assertIn("Library miss", version.rationale)
            self.assertIn("Template draft for 'Gravity'",
                          version.rationale)
            # SCRUM-78: tags, objective mapping, and rationale persist.
            self.assertEqual(list(version.objective_refs), ["falling bodies"])
            self.assertEqual(
                {(t.taxonomy, t.value) for t in version.tags},
                {(db.TagTaxonomy.subject, "physics"),
                 (db.TagTaxonomy.age_band, "10-12")})
            self.assertTrue(version.content_ref.startswith("sha256:"))
            body = FilesystemContentStore(
                self.content_root).get(version.content_ref)
            self.assertIn("Gravity", body["text"])
            self.assertEqual(
                version.directive_snapshot["directives"][0]["id"], 11)
            self.assertEqual(version.generation_run_id, result.run_id)
            run = s.get(db.GenerationRun, result.run_id)
            self.assertEqual(run.status, db.GenerationStatus.completed)
            artifacts = s.query(db.PreviewArtifact).filter_by(
                asset_version_id=result.version_id).all()
            self.assertEqual(len(artifacts), 1)
            self.assertEqual(artifacts[0].kind, db.PreviewKind.poster)
            self.assertEqual(artifacts[0].storage_ref, result.preview_ref)
        finally:
            s.close()
        self.assertTrue(
            (Path(self.preview_root) / result.preview_ref).is_file())

    def test_reuse_hit_returns_published_version_without_new_draft(self):
        # Companion: a strong library match reuses instead of generating.
        lib = SqlAlchemyAssetLibrary(self.sessions)
        runs = SqlAlchemyRunStore(self.sessions)
        run_id = runs.begin_run("a", "m", "p", {}, "policy/v1")
        ref = lib.save_draft(
            GeneratedContent(
                kind=AssetKind.text, title="Acids",
                body={"text": "acids"}, tags=(Tag("subject", "chemistry"),),
                objective_refs=("acids-bases",), rationale="seed"),
            "sha256:seed.json", {"directives": []}, run_id, self.user_id)
        s = self.sessions()
        before = s.query(db.AssetVersion).count()
        s.get(db.AssetVersion, ref.version_id).status = (
            db.VersionStatus.published)
        s.commit()
        s.close()

        backend = CountingBackend()
        pipe, _ = self.make_pipeline(backend)
        result = pipe.propose(
            GenerationRequest(
                kind=AssetKind.text,
                title="Acids revisited",
                objectives=("acids-bases",),
                tags=(Tag("subject", "chemistry"),),
                directives=(),
                parameters={},
            ),
            created_by_id=self.user_id,
        )
        self.assertTrue(result.reused)
        self.assertEqual(result.version_id, ref.version_id)
        self.assertEqual(backend.calls, 0)
        s = self.sessions()
        try:
            self.assertEqual(s.query(db.AssetVersion).count(), before)
            run = s.get(db.GenerationRun, result.run_id)
            self.assertEqual(run.status, db.GenerationStatus.completed)
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()
