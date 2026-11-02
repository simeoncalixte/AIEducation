"""Generation API service: asset proposals plus run tracking.

Composition root for the pipeline package: wires the real adapters
(SQLAlchemy library + runs, filesystem store, SVG previews, template
backend) behind a small Flask JSON API. Internal pilot service with
no auth; callers are trusted cluster peers.

Run (from the repository root)::

    PYTHONPATH=database:pipeline PORT=5002 \\
      service/.venv/bin/python -m evolvingclass_pipeline.app

``DATABASE_URL`` selects the database (default: ``pipeline/dev.db``);
``CONTENT_ROOT``/``PREVIEW_ROOT`` select the file stores; ``HOST``
selects the bind address.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

from flask import Flask, jsonify, request

import DataModels as db
from evolvingclass_pipeline.adapters.filesystem_content import (
    FilesystemContentStore,
)
from evolvingclass_pipeline.adapters.sqlalchemy_library import (
    SqlAlchemyAssetLibrary,
    SqlAlchemyRunStore,
)
from evolvingclass_pipeline.adapters.sqlalchemy_stages import (
    SqlAlchemyStageLibrary,
)
from evolvingclass_pipeline.adapters.svg_preview import SvgPreviewRenderer
from evolvingclass_pipeline.agents.template_backend import TemplateAssetBackend
from evolvingclass_pipeline.agents.template_stage import TemplateStageBackend
from evolvingclass_pipeline.asset_pipeline import AssetPipeline
from evolvingclass_pipeline.domain import (
    AssetKind,
    DirectiveInput,
    DirectiveKind,
    GenerationFailed,
    GenerationRequest,
    PolicyViolation,
    RunRecord,
    StageAssemblyRequest,
    Tag,
)
from evolvingclass_pipeline.policy import ContentPolicy
from evolvingclass_pipeline.stage_pipeline import StagePipeline
from evolvingclass_service.briefing import submit_brief
from evolvingclass_service.errors import PublicationError
from sqlalchemy.orm import sessionmaker

_RUN_STATUSES = frozenset(
    {"queued", "running", "completed", "failed", "cancelled"}
)
_MAX_LIMIT = 200


class _Invalid(Exception):
    """Request failed validation; mapped to a 400 payload."""


def _err(message: str, status: int, code: str | None = None):
    payload: dict[str, Any] = {"error": message}
    if code is not None:
        payload["code"] = code
    return jsonify(payload), status


def _str_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise _Invalid(f"'{field}' must be a list of strings.")
    return value


def _tags(value: Any) -> tuple[Tag, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _Invalid("'tags' must be a list.")
    tags = []
    for entry in value:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("taxonomy"), str)
            or not isinstance(entry.get("value"), str)
        ):
            raise _Invalid(
                "Each tag needs string 'taxonomy' and 'value'."
            )
        tags.append(Tag(entry["taxonomy"], entry["value"]))
    return tuple(tags)


def _directives(value: Any) -> tuple[DirectiveInput, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _Invalid("'directives' must be a list.")
    out = []
    for entry in value:
        try:
            kind = DirectiveKind(entry["kind"])
            ident = int(entry["id"])
            priority = int(entry.get("priority", 1))
            focus = entry["focus"]
            constraints = entry.get("constraints", {})
        except (KeyError, TypeError, ValueError):
            raise _Invalid(
                "Each directive needs int 'id', 'kind' brief|steer, "
                "string 'focus', int 'priority'."
            )
        if not isinstance(focus, str) or not isinstance(constraints, dict):
            raise _Invalid(
                "Each directive needs int 'id', 'kind' brief|steer, "
                "string 'focus', int 'priority'."
            )
        out.append(
            DirectiveInput(
                id=ident, kind=kind, focus=focus,
                constraints=dict(constraints), priority=priority,
            )
        )
    return tuple(out)


def _generate_request(body: Any) -> tuple[GenerationRequest, int]:
    if not isinstance(body, dict):
        raise _Invalid("Request body must be a JSON object.")
    try:
        kind = AssetKind(body.get("kind"))
    except ValueError:
        raise _Invalid(
            "'kind' must be one of: "
            + ", ".join(sorted(k.value for k in AssetKind))
            + "."
        )
    title = body.get("title", "")
    if not isinstance(title, str) or not title.strip():
        raise _Invalid("'title' must be a non-blank string.")
    try:
        created_by_id = int(body.get("created_by_id"))
    except (TypeError, ValueError):
        raise _Invalid("'created_by_id' must be an integer user id.")
    parameters = body.get("parameters", {})
    if not isinstance(parameters, dict):
        raise _Invalid("'parameters' must be an object.")
    return (
        GenerationRequest(
            kind=kind,
            title=title.strip(),
            objectives=tuple(_str_list(body.get("objectives"), "objectives")),
            tags=_tags(body.get("tags")),
            directives=_directives(body.get("directives")),
            parameters=dict(parameters),
        ),
        created_by_id,
    )


def _run_json(record: RunRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "agent_ref": record.agent_ref,
        "model_ref": record.model_ref,
        "prompt_ref": record.prompt_ref,
        "status": record.status,
        "attempts": record.attempts,
        "last_error": record.last_error,
        "params": dict(record.params),
        "policy_version": record.policy_version,
    }


def create_app(
    database_url: str | None = None,
    content_root: str | None = None,
    preview_root: str | None = None,
) -> Flask:
    """Build the generation API bound to ``database_url`` (or dev.db)."""
    here = os.path.dirname(os.path.abspath(__file__))
    url = (
        database_url
        or os.environ.get("DATABASE_URL")
        or f"sqlite:///{os.path.join(os.path.dirname(here), 'dev.db')}"
    )
    content_dir = content_root or os.environ.get(
        "CONTENT_ROOT", os.path.join(os.getcwd(), "var", "content")
    )
    preview_dir = preview_root or os.environ.get(
        "PREVIEW_ROOT", os.path.join(os.getcwd(), "var", "previews")
    )
    os.makedirs(content_dir, exist_ok=True)
    os.makedirs(preview_dir, exist_ok=True)
    sessions = db.get_session_factory(url)
    library = SqlAlchemyAssetLibrary(sessions)
    runs = SqlAlchemyRunStore(sessions)
    pipeline = AssetPipeline(
        library,
        TemplateAssetBackend(),
        SvgPreviewRenderer(preview_dir),
        runs,
        FilesystemContentStore(content_dir),
        policy=ContentPolicy(),
    )
    stages = StagePipeline(
        SqlAlchemyStageLibrary(sessions), TemplateStageBackend(), runs
    )

    app = Flask(__name__)
    app.config["runs"] = runs
    app.config["library"] = library

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"ok": True})

    @app.route("/api/generate/asset", methods=["POST"])
    def generate_asset():
        try:
            generation, created_by_id = _generate_request(
                request.get_json(silent=True)
            )
        except _Invalid as exc:
            return _err(str(exc), 400, "invalid_request")
        if not library.actor_exists(created_by_id):
            return _err("Unknown actor.", 404, "unknown_actor")
        try:
            result = pipeline.propose(generation, created_by_id)
        except GenerationFailed as exc:
            return _err(str(exc), 400, "generation_failed")
        except PolicyViolation as exc:
            return _err(f"Policy violated: {exc}", 422, "policy_violated")
        except LookupError as exc:
            return _err(str(exc), 404)
        return jsonify({
            "message": (
                "Proposal reused from library."
                if result.reused else "Proposal recorded."
            ),
            "reused": result.reused,
            "asset_id": result.asset_id,
            "version_id": result.version_id,
            "version_no": result.version_no,
            "run_id": result.run_id,
            "preview_ref": result.preview_ref,
        })

    @app.route("/api/generate/stage", methods=["POST"])
    def generate_stage():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return _err("Request body must be a JSON object.",
                        400, "invalid_request")
        try:
            lesson_id = int(body.get("lesson_id"))
        except (TypeError, ValueError):
            return _err("'lesson_id' must be an integer.",
                        400, "invalid_request")
        title = body.get("title", "")
        if not isinstance(title, str) or not title.strip():
            return _err("'title' must be a non-blank string.",
                        400, "invalid_request")
        try:
            created_by_id = int(body.get("created_by_id"))
        except (TypeError, ValueError):
            return _err("'created_by_id' must be an integer user id.",
                        400, "invalid_request")
        raw_ids = body.get("asset_version_ids", [])
        if not isinstance(raw_ids, list):
            return _err("'asset_version_ids' must be a list.",
                        400, "invalid_request")
        try:
            asset_ids = tuple(int(v) for v in raw_ids)
        except (TypeError, ValueError):
            return _err("'asset_version_ids' must hold integers.",
                        400, "invalid_request")
        try:
            objectives = tuple(
                _str_list(body.get("objectives"), "objectives"))
            directives = _directives(body.get("directives"))
        except _Invalid as exc:
            return _err(str(exc), 400, "invalid_request")
        parameters = body.get("parameters", {})
        if not isinstance(parameters, dict):
            return _err("'parameters' must be an object.",
                        400, "invalid_request")
        if not library.actor_exists(created_by_id):
            return _err("Unknown actor.", 404, "unknown_actor")
        try:
            result = stages.propose(
                StageAssemblyRequest(
                    title=title.strip(), lesson_id=lesson_id,
                    objectives=objectives, asset_version_ids=asset_ids,
                    directives=directives, parameters=dict(parameters),
                ),
                created_by_id,
            )
        except GenerationFailed as exc:
            return _err(str(exc), 400, "generation_failed")
        except LookupError as exc:
            return _err(str(exc), 404)
        return jsonify({
            "message": "Stage assembly recorded.",
            "stage_id": result.stage_id,
            "version_id": result.version_id,
            "version_no": result.version_no,
            "run_id": result.run_id,
        })

    @app.route("/api/generate/lesson", methods=["POST"])
    def generate_lesson():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return _err("Request body must be a JSON object.",
                        400, "invalid_request")
        try:
            lesson_id = int(body.get("lesson_id"))
        except (TypeError, ValueError):
            return _err("'lesson_id' must be an integer.",
                        400, "invalid_request")
        try:
            actor_id = int(body.get("created_by_id"))
        except (TypeError, ValueError):
            return _err("'created_by_id' must be an integer user id.",
                        400, "invalid_request")
        raw_student = body.get("student_id")
        try:
            student_id = None if raw_student is None else int(raw_student)
        except (TypeError, ValueError):
            return _err("'student_id' must be an integer or null.",
                        400, "invalid_request")
        try:
            objectives = _str_list(body.get("objectives"), "objectives")
            models = _str_list(body.get("mental_models"), "mental_models")
        except _Invalid as exc:
            return _err(str(exc), 400, "invalid_request")
        focus = body.get("focus", "")
        if not isinstance(focus, str):
            return _err("'focus' must be a string.",
                        400, "invalid_request")
        constraints = body.get("constraints", {})
        if not isinstance(constraints, dict):
            return _err("'constraints' must be an object.",
                        400, "invalid_request")
        try:
            priority = int(body.get("priority", 1))
        except (TypeError, ValueError):
            return _err("'priority' must be an integer.",
                        400, "invalid_request")
        try:
            result = submit_brief(
                sessions, lesson_id, actor_id,
                objectives=objectives, mental_models=models, focus=focus,
                constraints=dict(constraints), priority=priority,
                student_id=student_id,
            )
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return _err(str(exc), status, exc.code)
        return jsonify({
            "message": "Lesson draft recorded.",
            "directive_id": result.directive_id,
            "lesson_version_id": result.lesson_version_id,
            "version_no": result.version_no,
            "run_id": result.run_id,
        })

    @app.route("/api/runs", methods=["GET"])
    def list_runs():
        status = request.args.get("status")
        if status is not None and status not in _RUN_STATUSES:
            return _err(
                "'status' must be one of: "
                + ", ".join(sorted(_RUN_STATUSES)) + ".",
                400, "invalid_request",
            )
        try:
            limit = int(request.args.get("limit", "50"))
        except ValueError:
            return _err("'limit' must be an integer.", 400, "invalid_request")
        limit = max(1, min(_MAX_LIMIT, limit))
        return jsonify({
            "runs": [_run_json(r) for r in runs.list_runs(status, limit)]
        })

    @app.route("/api/runs/<int:run_id>", methods=["GET"])
    def get_run(run_id: int):
        try:
            record = runs.get_run(run_id)
        except LookupError as exc:
            return _err(str(exc), 404)
        return jsonify({"run": _run_json(record)})

    return app


def ensure_schema(database_url: str) -> None:
    """Create tables when the generation database is brand new."""
    engine = db.get_engine(database_url)
    db.Base.metadata.create_all(engine)
    engine.dispose()


if __name__ == "__main__":
    _url = os.environ.get("DATABASE_URL")
    if _url is None:
        _here = os.path.dirname(os.path.abspath(__file__))
        _url = f"sqlite:///{os.path.join(os.path.dirname(_here), 'dev.db')}"
    ensure_schema(_url)
    create_app(_url).run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5002")),
    )
