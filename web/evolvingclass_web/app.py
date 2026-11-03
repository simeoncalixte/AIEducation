"""EvolvingClass JSON API server: Flask factory with /api/* routes only.

React (``frontend/``) owns every page; this app serves no HTML. Run
(from the repository root)::

    PYTHONPATH=database:pipeline:service:web PORT=5001 \\
      service/.venv/bin/python -m evolvingclass_web.app

``DATABASE_URL`` selects the database (default: ``web/dev.db``);
``FLASK_SECRET`` sets the session key; ``PREVIEW_DIR`` enables
publish-time preview rendering.
"""

from __future__ import annotations

import os

from flask import (
    Flask,
    g,
    jsonify,
    request,
    session as flask_session,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from DataModels import Base

from . import present
from .api import register_api

_PUBLIC_API = frozenset({
    "api_health", "api_session", "api_login_choices", "api_login",
    # Registered only when ALLOW_TEST_RESET=1 (live interaction suite).
    "api_test_reset",
})


def create_app(database_url: str | None = None) -> Flask:
    """Build the JSON API app bound to ``database_url`` (or dev.db)."""
    here = os.path.dirname(os.path.abspath(__file__))
    url = (
        database_url
        or os.environ.get("DATABASE_URL")
        or f"sqlite:///{os.path.join(os.path.dirname(here), 'dev.db')}"
    )
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET", "dev-review-secret")
    connect_args = {"check_same_thread": False} if "sqlite" in url else {}
    engine = create_engine(url, connect_args=connect_args)
    app.config["engine"] = engine
    app.config["make_session"] = sessionmaker(bind=engine)
    app.config["preview_dir"] = os.environ.get("PREVIEW_DIR")
    app.config["database_url"] = url

    @app.teardown_appcontext
    def _close_session(_exc: BaseException | None) -> None:
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def db():
        if "db" not in g:
            g.db = app.config["make_session"]()
        return g.db

    def actor_id() -> int | None:
        return flask_session.get("actor_id")

    def current_user() -> dict | None:
        if "user" not in g:
            g.user = present.current_actor(db(), actor_id())
        return g.user

    @app.before_request
    def _guard():
        if not request.path.startswith("/api/"):
            return None
        if request.endpoint in _PUBLIC_API:
            return None
        if current_user() is None:
            return jsonify({"error": "Log in first."}), 401
        return None

    @app.errorhandler(404)
    def _not_found(_exc):
        return jsonify({"error": "Not found."}), 404

    register_api(app, db, current_user)

    return app


def ensure_schema(database_url: str) -> None:
    """Create tables when the review database is brand new."""
    connect_args = {"check_same_thread": False} if "sqlite" in database_url else {}
    Base.metadata.create_all(create_engine(database_url,
                                           connect_args=connect_args))


if __name__ == "__main__":
    _here = os.path.dirname(os.path.abspath(__file__))
    _url = os.environ.get("DATABASE_URL") or (
        f"sqlite:///{os.path.join(os.path.dirname(_here), 'dev.db')}")
    ensure_schema(_url)
    create_app(_url).run(host=os.environ.get("HOST", "127.0.0.1"),
                         port=int(os.environ.get("PORT", "5000")))
