"""EvolvingClass web app: Flask factory, routes, and actions.

Run (from the repository root)::

    PYTHONPATH=database:pipeline:service:web PORT=5001 \\
      service/.venv/bin/python -m evolvingclass_web.app

Then open http://127.0.0.1:5001 in a browser and log in with a pilot
login name. ``DATABASE_URL`` selects the database (default:
``web/dev.db``); ``FLASK_SECRET`` sets the session key; ``PREVIEW_DIR``
enables publish-time preview rendering.
"""

from __future__ import annotations

import os

from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session as flask_session,
    url_for,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from DataModels import AssetVersion, Base, Decision, StageVersion
from evolvingclass_pipeline.adapters.svg_preview import SvgPreviewRenderer
from evolvingclass_pipeline.domain import PreviewRequest
from evolvingclass_service import (
    PublicationError,
    answer_challenge,
    assign_lesson,
    create_steer_directive,
    deactivate_directive,
    finish_attempt,
    flag_misconception,
    publish_asset_version,
    publish_lesson_version,
    publish_stage_version,
    rate_lesson,
    record_approval,
    record_verdict_override,
    retire_asset_version,
    retry_attempt,
    retire_lesson_version,
    retire_stage_version,
    revise_asset_version,
    rollback_asset_version,
    rollback_lesson_version,
    rollback_stage_version,
    start_attempt,
    submit_brief,
    update_directive,
    update_draft,
)

from . import present
from .api import register_api

_PUBLISH = {
    "asset": publish_asset_version,
    "stage": publish_stage_version,
    "lesson": publish_lesson_version,
}
_ROLLBACK = {
    "asset": rollback_asset_version,
    "stage": rollback_stage_version,
    "lesson": rollback_lesson_version,
}
_RETIRE = {
    "asset": retire_asset_version,
    "stage": retire_stage_version,
    "lesson": retire_lesson_version,
}

_PUBLIC_ENDPOINTS = frozenset({"login", "logout", "static"})

_PUBLIC_API = frozenset({
    "api_health", "api_session", "api_login_choices", "api_login",
    # Registered only when ALLOW_TEST_RESET=1 (live interaction suite).
    "api_test_reset",
})

_ADMIN_ONLY = frozenset({"audit"})

_TEACHER_ONLY = frozenset({
    "queues", "lessons", "brief", "version_detail", "approve", "reject",
    "edit", "publish", "rollback", "retire", "revise_asset",
    "directives", "directive_edit", "directive_deactivate",
    "override_verdict", "flag_attempt",
    "assignments", "assignment_detail",
})


def create_app(database_url: str | None = None) -> Flask:
    """Build the review app bound to ``database_url`` (or dev.db)."""
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

    @app.context_processor
    def _inject_user():
        try:
            user = current_user()
        except Exception:
            user = None
        return {"current_user": user}

    @app.errorhandler(404)
    def _not_found(_exc):
        return render_template(
            "error.html", code=404,
            message="This page does not exist."), 404

    @app.route("/")
    def index():
        if current_user() is None:
            return redirect(url_for("login"))
        return redirect(url_for("home"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        """Pilot login by login name; passwords arrive with school SSO."""
        if request.method == "POST":
            ref = (request.form.get("login_ref") or "").strip()
            user = present.find_by_login(db(), ref)
            if user is None:
                flash("Unknown login; pick a pilot user below.")
                return render_template(
                    "login.html", users=present.login_choices(db()))
            flask_session["actor_id"] = user["id"]
            g.pop("user", None)
            flash(f"Logged in as {user['name']} ({user['role']}).")
            return redirect(url_for("home"))
        if current_user() is not None:
            return redirect(url_for("home"))
        return render_template(
            "login.html", users=present.login_choices(db()))

    @app.route("/logout")
    def logout():
        flask_session.pop("actor_id", None)
        g.pop("user", None)
        flash("Logged out.")
        return redirect(url_for("login"))

    @app.route("/home")
    def home():
        user = current_user()
        assignments = (
            present.student_assignments(db(), user["id"])
            if user["role"] == "student" else []
        )
        return render_template("home.html", user=user,
                               assignments=assignments)

    def _play_allowed(attempt_id: int, mutate: bool):
        """Attempt access: owner always, teachers read-only preview."""
        user = current_user()
        owner = present.attempt_owner(db(), attempt_id)
        if owner is None:
            return None, ("Unknown attempt", 404)
        if user["id"] == owner:
            return owner, None
        if not mutate and user["role"] in ("teacher", "admin"):
            return owner, None
        return None, ("error.html", 403)

    def _play_denied(denied):
        template, code = denied
        if template == "error.html":
            return render_template(
                "error.html", code=403,
                message="This attempt belongs to another student."), 403
        return template, code

    @app.route("/play/<int:assignment_id>")
    def play_briefing(assignment_id: int):
        user = current_user()
        briefing = present.briefing(db(), assignment_id, user["id"])
        if briefing is None:
            return "Unknown assignment", 404
        return render_template("briefing.html", b=briefing)

    @app.route("/play/<int:assignment_id>/start", methods=["POST"])
    def play_start(assignment_id: int):
        make = app.config["make_session"]
        try:
            attempt_id = start_attempt(make, assignment_id, actor_id())
        except PublicationError as exc:
            flash(f"Start rejected ({exc.code}): {exc}")
            return redirect(url_for("play_briefing",
                                    assignment_id=assignment_id))
        if present.challenge_view(db(), attempt_id, 1) is None:
            return redirect(url_for("play_debrief", attempt_id=attempt_id))
        return redirect(url_for("play_challenge", attempt_id=attempt_id,
                                index=1))

    @app.route("/play/attempt/<int:attempt_id>/challenge/<int:index>",
               methods=["GET", "POST"])
    def play_challenge(attempt_id: int, index: int):
        mutate = request.method == "POST"
        _, denied = _play_allowed(attempt_id, mutate)
        if denied is not None:
            return _play_denied(denied)
        view = present.challenge_view(db(), attempt_id, index)
        if view is None:
            return "Unknown challenge", 404
        if mutate:
            make = app.config["make_session"]
            try:
                answer_challenge(
                    make, attempt_id, actor_id(),
                    view["challenge_version_id"],
                    request.form.getlist("goals"),
                    note=request.form.get("note", ""))
            except PublicationError as exc:
                flash(f"Answer rejected ({exc.code}): {exc}")
                return redirect(url_for("play_challenge",
                                        attempt_id=attempt_id, index=index))
            if index < view["total"]:
                return redirect(url_for("play_challenge",
                                        attempt_id=attempt_id,
                                        index=index + 1))
            return redirect(url_for("play_debrief", attempt_id=attempt_id))
        return render_template("challenge.html", c=view)

    @app.route("/play/attempt/<int:attempt_id>/debrief")
    def play_debrief(attempt_id: int):
        _, denied = _play_allowed(attempt_id, False)
        if denied is not None:
            return _play_denied(denied)
        view = present.debrief_view(db(), attempt_id)
        if view is None:
            return "Unknown attempt", 404
        return render_template("debrief.html", d=view)

    @app.route("/play/attempt/<int:attempt_id>/finish", methods=["POST"])
    def play_finish(attempt_id: int):
        _, denied = _play_allowed(attempt_id, True)
        if denied is not None:
            return _play_denied(denied)
        make = app.config["make_session"]
        try:
            finish_attempt(make, attempt_id, actor_id())
        except PublicationError as exc:
            flash(f"Finish rejected ({exc.code}): {exc}")
        else:
            flash("Attempt finished.")
        return redirect(url_for("play_debrief", attempt_id=attempt_id))

    @app.route("/play/attempt/<int:attempt_id>/rate", methods=["POST"])
    def play_rate(attempt_id: int):
        _, denied = _play_allowed(attempt_id, True)
        if denied is not None:
            return _play_denied(denied)
        make = app.config["make_session"]
        try:
            score = int(request.form.get("score", "0"))
        except ValueError:
            score = 0
        try:
            rate_lesson(make, attempt_id, actor_id(), score)
        except PublicationError as exc:
            flash(f"Rating rejected ({exc.code}): {exc}")
        else:
            flash("Rating recorded.")
        return redirect(url_for("play_debrief", attempt_id=attempt_id))

    @app.route("/play/attempt/<int:attempt_id>/retry", methods=["POST"])
    def play_retry(attempt_id: int):
        _, denied = _play_allowed(attempt_id, True)
        if denied is not None:
            return _play_denied(denied)
        make = app.config["make_session"]
        try:
            new_id = retry_attempt(make, attempt_id, actor_id())
        except PublicationError as exc:
            flash(f"Retry rejected ({exc.code}): {exc}")
            return redirect(url_for("play_debrief", attempt_id=attempt_id))
        flash("Retry started.")
        if present.challenge_view(db(), new_id, 1) is None:
            return redirect(url_for("play_debrief", attempt_id=new_id))
        return redirect(url_for("play_challenge", attempt_id=new_id,
                                index=1))

    @app.before_request
    def _guard():
        if request.path.startswith("/api/"):
            if request.endpoint in _PUBLIC_API:
                return None
            if current_user() is None:
                return jsonify({"error": "Log in first."}), 401
            return None
        if request.endpoint in _PUBLIC_ENDPOINTS:
            return None
        user = current_user()
        if user is None:
            flask_session.pop("actor_id", None)
            return redirect(url_for("login"))
        if (request.endpoint in _TEACHER_ONLY
                and user["role"] not in ("teacher", "admin")):
            return render_template(
                "error.html", code=403,
                message="This area is for teachers and admins."), 403
        if request.endpoint in _ADMIN_ONLY and user["role"] != "admin":
            return render_template(
                "error.html", code=403,
                message="This area is for school admins."), 403
        return None

    @app.route("/review")
    def queues():
        return render_template("queues.html",
                               queues=present.queue_rows(db()))

    @app.route("/lessons")
    def lessons():
        return render_template("lessons.html",
                               lessons=present.lesson_list(db()))

    @app.route("/lessons/<int:lesson_id>/brief", methods=["GET", "POST"])
    def brief(lesson_id: int):
        ctx = present.brief_context(db(), lesson_id)
        if ctx is None:
            return "Unknown lesson", 404
        if request.method == "POST":
            make = app.config["make_session"]
            try:
                result = submit_brief(
                    make,
                    lesson_id=lesson_id,
                    actor_id=actor_id(),
                    objectives=_lines(request.form.get("objectives", "")),
                    mental_models=_lines(
                        request.form.get("mental_models", "")),
                    focus=request.form.get("focus", ""),
                    constraints=_constraints(request.form),
                    priority=_priority(request.form.get("priority", "1")),
                    student_id=_student_id(
                        request.form.get("student_id", "")),
                )
            except PublicationError as exc:
                flash(f"Brief rejected ({exc.code}): {exc}")
                return render_template("brief.html", lesson=ctx,
                                       form=request.form)
            flash("Brief recorded.")
            return redirect(url_for("version_detail", kind="lesson",
                                    version_id=result.lesson_version_id))
        return render_template("brief.html", lesson=ctx, form=request.form)

    @app.route("/lessons/<int:lesson_id>/directives",
                methods=["GET", "POST"])
    def directives(lesson_id: int):
        ctx = present.brief_context(db(), lesson_id)
        if ctx is None:
            return "Unknown lesson", 404
        if request.method == "POST":
            make = app.config["make_session"]
            try:
                create_steer_directive(
                    make,
                    lesson_id=lesson_id,
                    actor_id=actor_id(),
                    focus=request.form.get("focus", ""),
                    constraints=_constraints(request.form),
                    priority=_priority(request.form.get("priority", "1")),
                    student_id=_student_id(
                        request.form.get("student_id", "")),
                )
            except PublicationError as exc:
                flash(f"Directive rejected ({exc.code}): {exc}")
            else:
                flash("Directive recorded.")
            return redirect(url_for("directives", lesson_id=lesson_id))
        return render_template("directives.html", lesson=ctx)

    @app.route("/directives/<int:directive_id>/edit",
               methods=["GET", "POST"])
    def directive_edit(directive_id: int):
        d = present.directive_detail(db(), directive_id)
        if d is None:
            return "Unknown directive", 404
        if request.method == "POST":
            make = app.config["make_session"]
            try:
                update_directive(
                    make, directive_id, actor_id(),
                    focus=request.form.get("focus", ""),
                    constraints=_constraints(request.form),
                    priority=_priority(request.form.get("priority", "1")),
                )
            except PublicationError as exc:
                flash(f"Directive rejected ({exc.code}): {exc}")
                return render_template("directive_edit.html", d=d,
                                       form=request.form)
            flash("Directive updated.")
            return redirect(url_for("directives",
                                    lesson_id=d["lesson_id"]))
        return render_template("directive_edit.html", d=d, form=None)

    @app.route("/directives/<int:directive_id>/deactivate",
               methods=["POST"])
    def directive_deactivate(directive_id: int):
        d = present.directive_detail(db(), directive_id)
        if d is None:
            return "Unknown directive", 404
        make = app.config["make_session"]
        try:
            deactivate_directive(make, directive_id, actor_id())
        except PublicationError as exc:
            flash(f"Directive rejected ({exc.code}): {exc}")
        else:
            flash("Directive deactivated.")
        return redirect(url_for("directives", lesson_id=d["lesson_id"]))

    @app.route("/assignments", methods=["GET", "POST"])
    def assignments():
        if request.method == "POST":
            make = app.config["make_session"]
            try:
                aid = assign_lesson(
                    make,
                    lesson_id=_optional_id(
                        request.form.get("lesson_id", "")) or 0,
                    actor_id=actor_id(),
                    classroom_id=_optional_id(
                        request.form.get("classroom_id", "")),
                    student_id=_optional_id(
                        request.form.get("student_id", "")),
                )
            except PublicationError as exc:
                flash(f"Assignment rejected ({exc.code}): {exc}")
                return render_template(
                    "assignments.html",
                    assignments=present.assignment_list(db()),
                    options=present.assignment_options(db()),
                    form=request.form)
            flash("Assignment recorded.")
            return redirect(url_for("assignment_detail",
                                    assignment_id=aid))
        return render_template(
            "assignments.html",
            assignments=present.assignment_list(db()),
            options=present.assignment_options(db()),
            form=None)

    @app.route("/assignments/<int:assignment_id>")
    def assignment_detail(assignment_id: int):
        progress = present.assignment_progress(db(), assignment_id)
        if progress is None:
            return "Unknown assignment", 404
        return render_template("assignment_detail.html", a=progress)

    @app.route("/audit")
    def audit():
        actor = _optional_id(request.args.get("actor", ""))
        since = _parse_date(request.args.get("since", ""))
        until = _parse_date(request.args.get("until", ""))
        return render_template(
            "audit.html",
            status=present.school_status(db()),
            trail=present.audit_trail(db(), actor_id=actor,
                                      since=since, until=until),
            actors=present.audit_actors(db()),
            filters={"actor": actor, "since": since, "until": until})

    @app.route("/review/<kind>/<int:version_id>")
    def version_detail(kind: str, version_id: int):
        if kind not in present.KINDS:
            return "Unknown level", 404
        dossier = present.detail(db(), kind, version_id)
        if dossier is None:
            return "Unknown version", 404
        return render_template("detail.html", d=dossier)

    def _run(action: str, kind: str, version_id: int, fn) -> object:
        try:
            fn()
        except PublicationError as exc:
            flash(f"{action} rejected ({exc.code}): {exc}")
        else:
            flash(f"{action} recorded.")
        return redirect(url_for("version_detail", kind=kind,
                                version_id=version_id))

    @app.route("/review/<kind>/<int:version_id>/approve", methods=["POST"])
    def approve(kind: str, version_id: int):
        make = app.config["make_session"]
        return _run("Approval", kind, version_id, lambda: record_approval(
            make, kind, version_id, actor_id(),
            Decision.approved, request.form.get("rationale", "")))

    @app.route("/review/<kind>/<int:version_id>/reject", methods=["POST"])
    def reject(kind: str, version_id: int):
        make = app.config["make_session"]
        return _run("Rejection", kind, version_id, lambda: record_approval(
            make, kind, version_id, actor_id(),
            Decision.rejected, request.form.get("rationale", "")))

    @app.route("/review/<kind>/<int:version_id>/edit", methods=["GET", "POST"])
    def edit(kind: str, version_id: int):
        if kind not in present.KINDS:
            return "Unknown level", 404
        dossier = present.detail(db(), kind, version_id)
        if dossier is None:
            return "Unknown version", 404
        if request.method == "POST":
            make = app.config["make_session"]
            return _run("Edit", kind, version_id, lambda: update_draft(
                make, kind, version_id, actor_id(),
                rationale=request.form.get("rationale"),
                content_ref=request.form.get("content_ref") or None
                if kind == "asset" else None))
        return render_template("edit.html", d=dossier)

    def finalize_preview(kind: str, version_id: int):
        """Render the publish-time poster, or None when unconfigured."""
        preview_dir = app.config.get("preview_dir")
        if not preview_dir:
            return None
        with app.config["make_session"]() as session:
            if kind == "asset":
                version = session.get(AssetVersion, version_id)
                subject_id, namespace = version.asset_id, ""
                title = version.asset.title
            else:
                version = session.get(StageVersion, version_id)
                subject_id, namespace = version.stage_id, "stage"
                title = (f"{version.stage.lesson.title} / "
                         f"{version.stage.title}")
            result = SvgPreviewRenderer(preview_dir).render(PreviewRequest(
                asset_id=subject_id, version_id=version.id,
                version_no=version.version_no, kind="poster", title=title,
                metadata={}, namespace=namespace,
            ))
            return ("poster", result.storage_ref)

    @app.route("/review/<kind>/<int:version_id>/publish", methods=["POST"])
    def publish(kind: str, version_id: int):
        make = app.config["make_session"]
        extra = {"finalize_preview": finalize_preview} if kind in (
            "asset", "stage") else {}
        return _run("Publication", kind, version_id, lambda: _PUBLISH[kind](
            make, version_id, actor_id(),
            request.form.get("rationale", ""), **extra))

    @app.route("/review/<kind>/<int:version_id>/rollback", methods=["POST"])
    def rollback(kind: str, version_id: int):
        make = app.config["make_session"]
        return _run("Rollback", kind, version_id, lambda: _ROLLBACK[kind](
            make, version_id, actor_id(),
            request.form.get("rationale", "")))

    @app.route("/review/<kind>/<int:version_id>/retire", methods=["POST"])
    def retire(kind: str, version_id: int):
        make = app.config["make_session"]
        return _run("Retirement", kind, version_id, lambda: _RETIRE[kind](
            make, version_id, actor_id(),
            request.form.get("rationale", "")))

    @app.route("/verdicts/<int:event_id>/override", methods=["POST"])
    def override_verdict(event_id: int):
        make = app.config["make_session"]
        nxt = request.form.get("next") or ""
        if not nxt.startswith("/"):
            nxt = url_for("home")
        try:
            record_verdict_override(
                make, event_id, actor_id(),
                reason=request.form.get("reason", ""),
                corrected_passed=request.form.get("corrected") == "pass",
                corrected_score=_score(request.form.get("score", "")),
            )
        except PublicationError as exc:
            flash(f"Override rejected ({exc.code}): {exc}")
        else:
            flash("Override recorded.")
        return redirect(nxt)

    @app.route("/attempts/<int:attempt_id>/flag", methods=["POST"])
    def flag_attempt(attempt_id: int):
        make = app.config["make_session"]
        nxt = request.form.get("next") or ""
        if not nxt.startswith("/"):
            nxt = url_for("home")
        raw = (request.form.get("misconception_id") or "").strip()
        try:
            flag_misconception(
                make, attempt_id, actor_id(),
                misconception_id=int(raw) if raw.isdigit() else None,
                note=request.form.get("note", ""),
            )
        except PublicationError as exc:
            flash(f"Flag rejected ({exc.code}): {exc}")
        else:
            flash("Flag recorded.")
        return redirect(nxt)

    @app.route("/review/asset/<int:version_id>/revise", methods=["POST"])
    def revise_asset(version_id: int):
        make = app.config["make_session"]
        try:
            new_id = revise_asset_version(
                make, version_id, actor_id(),
                request.form.get("rationale", ""))
        except PublicationError as exc:
            flash(f"Revision rejected ({exc.code}): {exc}")
            return redirect(url_for("version_detail", kind="asset",
                                    version_id=version_id))
        flash("Revision drafted.")
        return redirect(url_for("version_detail", kind="asset",
                                version_id=new_id))

    register_api(app, db, current_user)

    return app


def _lines(raw: str) -> list[str]:
    """One item per line, blanks dropped."""
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _split_items(raw: str) -> list[str]:
    """Comma- or line-separated constraint items, blanks dropped."""
    return [chunk.strip() for chunk in raw.replace("\n", ",").split(",")
            if chunk.strip()]


def _constraints(form) -> dict:
    constraints: dict[str, list[str]] = {}
    include = _split_items(form.get("must_include", ""))
    avoid = _split_items(form.get("must_avoid", ""))
    if include:
        constraints["must_include"] = include
    if avoid:
        constraints["must_avoid"] = avoid
    return constraints


def _priority(raw: str) -> int:
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


def _student_id(raw: str) -> int | None:
    """Scope selector value: blank means class-wide."""
    return _optional_id(raw)


def _optional_id(raw: str) -> int | None:
    """Form id selector: blank or garbage means unset."""
    raw = (raw or "").strip()
    return int(raw) if raw.isdigit() else None


def _parse_date(raw: str):
    """YYYY-MM-DD query value, or None when blank or invalid."""
    import datetime as _dt

    try:
        return _dt.date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


def _score(raw: str) -> float | None:
    """Optional 0–1 score field; blank or garbage means no score."""
    try:
        return float((raw or "").strip())
    except ValueError:
        return None


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
