"""JSON API for the React frontend (SCRUM-173, page by page).

Reads go through :mod:`evolvingclass_web.present` view models (plain
dicts, JSON-safe); writes go through ``evolvingclass_service`` — the
same thin-handler split as the Flask page routes. Session cookie auth
is unchanged: logged-out calls get JSON 401s (see ``_guard`` in
:appmod:`evolvingclass_web.app`) and role violations get JSON 403s.
"""

from __future__ import annotations

import os

from flask import Flask, g, jsonify, request
from flask import session as flask_session

from DataModels import (
    AssetVersion,
    Attempt,
    Decision,
    ExperienceEvent,
    StageVersion,
)
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
    latest_checkpoint,
    rate_lesson,
    record_approval,
    record_client_event,
    save_checkpoint,
    record_teacher_evaluation,
    record_verdict_override,
    update_lesson_composition,
    update_stage_uses,
    retire_asset_version,
    retire_lesson_version,
    retire_stage_version,
    retry_attempt,
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


def _err(message: str, status: int):
    return jsonify({"error": message}), status


def _brief_lines(value) -> list[str]:
    """One item per line (or per list entry), blanks dropped."""
    if isinstance(value, str):
        items = value.splitlines()
    elif isinstance(value, (list, tuple)):
        items = [str(item) for item in value]
    else:
        return []
    return [item.strip() for item in items if item.strip()]


def _brief_items(value) -> list[str]:
    """Comma- or line-separated items (or a list), blanks dropped."""
    if isinstance(value, str):
        value = value.replace("\n", ",").split(",")
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _brief_priority(value) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _brief_student_id(value) -> int | None:
    """Scope selector: blank or missing means class-wide."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    raw = str(value).strip()
    return int(raw) if raw.isdigit() else None


def register_api(app: Flask, db, current_user) -> None:
    """Add the ``/api/*`` JSON routes bound to the app's helpers."""

    @app.route("/api/health", methods=["GET"], endpoint="api_health")
    def api_health():
        return jsonify({"ok": True})

    if os.environ.get("ALLOW_TEST_RESET") == "1":
        @app.route("/api/__test__/reset", methods=["POST"],
                   endpoint="api_test_reset")
        def api_test_reset():
            """Restore seeded demo data for the live interaction suite.

            Test-only: the route exists solely when ALLOW_TEST_RESET=1
            (set by test-live.sh) and refuses non-sqlite databases, so
            a real database can never be wiped through it.
            """
            from sqlalchemy import create_engine

            from DataModels import Base

            from .seed import seed

            url = app.config.get("database_url", "")
            if "sqlite" not in url:
                return _err("Test reset supports sqlite only.", 403)
            old = g.pop("db", None)
            if old is not None:
                old.close()
            live = app.config.get("engine")
            if live is not None:
                live.dispose()
            engine = create_engine(
                url, connect_args={"check_same_thread": False})
            try:
                Base.metadata.drop_all(engine)
            finally:
                engine.dispose()
            seed(url)
            return jsonify({"ok": True})

    @app.route("/api/session", methods=["GET"], endpoint="api_session")
    def api_session():
        return jsonify({"user": current_user()})

    @app.route("/api/login_choices", methods=["GET"],
               endpoint="api_login_choices")
    def api_login_choices():
        return jsonify({"users": present.login_choices(db())})

    @app.route("/api/login", methods=["POST"], endpoint="api_login")
    def api_login():
        payload = request.get_json(silent=True) or {}
        ref = (payload.get("login_ref")
               if isinstance(payload, dict) else None)
        if ref is None:
            ref = request.form.get("login_ref", "")
        ref = (ref or "").strip()
        user = present.find_by_login(db(), ref)
        if user is None:
            return _err("Unknown login; pick a pilot user below.", 401)
        flask_session["actor_id"] = user["id"]
        g.pop("user", None)
        return jsonify({
            "user": user,
            "message": f"Logged in as {user['name']} ({user['role']}).",
        })

    @app.route("/api/logout", methods=["POST"], endpoint="api_logout")
    def api_logout():
        flask_session.pop("actor_id", None)
        g.pop("user", None)
        return jsonify({"ok": True, "message": "Logged out."})

    @app.route("/api/home", methods=["GET"], endpoint="api_home")
    def api_home():
        user = current_user()
        if user is None:  # pragma: no cover - _guard answers first
            return _err("Log in first.", 401)
        if user["role"] in ("teacher", "admin"):
            links = [
                {"href": "/review", "label": "Review queues",
                 "blurb": "approve asset, stage, and lesson proposals"},
                {"href": "/lessons", "label": "Lessons",
                 "blurb": "brief lessons for agent drafting"},
                {"href": "/assignments", "label": "Assignments",
                 "blurb": "assign lessons and monitor progress"},
            ]
            if user["role"] == "admin":
                links.append(
                    {"href": "/audit", "label": "Audit",
                     "blurb": "school-wide status and approval history"})
            return jsonify({"user": user, "links": links})
        return jsonify({
            "user": user,
            "assignments": present.student_assignments(db(), user["id"]),
        })

    @app.route("/api/review", methods=["GET"], endpoint="api_review")
    def api_review():
        user = current_user()
        if user is None:  # pragma: no cover - _guard answers first
            return _err("Log in first.", 401)
        if user["role"] not in ("teacher", "admin"):
            return _err("This area is for teachers and admins.", 403)
        return jsonify({"queues": present.queue_rows(db())})

    @app.route("/api/lessons", methods=["GET"], endpoint="api_lessons")
    def api_lessons():
        user = current_user()
        if user is None:  # pragma: no cover - _guard answers first
            return _err("Log in first.", 401)
        if user["role"] not in ("teacher", "admin"):
            return _err("This area is for teachers and admins.", 403)
        return jsonify({"lessons": present.lesson_list(db())})

    @app.route("/api/audit", methods=["GET"], endpoint="api_audit")
    def api_audit():
        _, denied = _admin()
        if denied is not None:
            return denied
        actor = _audit_actor(request.args.get("actor", ""))
        since = _audit_date(request.args.get("since", ""))
        until = _audit_date(request.args.get("until", ""))
        return jsonify({
            "status": present.school_status(db()),
            "trail": present.audit_trail(
                db(), actor_id=actor, since=since, until=until),
            "actors": present.audit_actors(db()),
            "filters": {
                "actor": actor,
                "since": since.isoformat() if since is not None else None,
                "until": until.isoformat() if until is not None else None,
            },
        })

    @app.route("/api/assignments", methods=["GET"],
               endpoint="api_assignments")
    def api_assignments():
        _, denied = _staff()
        if denied is not None:
            return denied
        return jsonify({
            "assignments": present.assignment_list(db()),
            "options": present.assignment_options(db()),
        })

    @app.route("/api/assignments", methods=["POST"],
               endpoint="api_assignments_create")
    def api_assignments_create():
        _, denied = _staff()
        if denied is not None:
            return denied
        payload = _payload()
        try:
            assignment_id = assign_lesson(
                app.config["make_session"],
                lesson_id=_assignment_id(payload.get("lesson_id")) or 0,
                actor_id=_actor_id(),
                classroom_id=_assignment_id(
                    payload.get("classroom_id")),
                student_id=_assignment_id(payload.get("student_id")),
            )
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify(
                {"error": f"Assignment rejected ({exc.code}): {exc}",
                 "code": exc.code}), status
        fresh = _assignments_payload()
        return jsonify({"message": "Assignment recorded.",
                        "assignment_id": assignment_id,
                        "assignments": fresh["assignments"],
                        "options": fresh["options"]})

    @app.route("/api/assignments/<int:assignment_id>", methods=["GET"],
               endpoint="api_assignment_progress")
    def api_assignment_progress(assignment_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        progress = present.assignment_progress(db(), assignment_id)
        if progress is None:
            return _err("Unknown assignment", 404)
        return jsonify({"progress": progress})

    @app.route("/api/play/<int:assignment_id>", methods=["GET"],
               endpoint="api_play_briefing")
    def api_play_briefing(assignment_id: int):
        user = current_user()
        if user is None:  # pragma: no cover - _guard answers first
            return _err("Log in first.", 401)
        briefing = present.briefing(db(), assignment_id, user["id"])
        if briefing is None:
            return _err("Unknown assignment", 404)
        return jsonify({"briefing": briefing})

    @app.route("/api/play/<int:assignment_id>/start", methods=["POST"],
               endpoint="api_play_start")
    def api_play_start(assignment_id: int):
        user = current_user()
        if user is None:  # pragma: no cover - _guard answers first
            return _err("Log in first.", 401)
        try:
            attempt_id = start_attempt(
                app.config["make_session"], assignment_id, user["id"])
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify(
                {"error": f"Start rejected ({exc.code}): {exc}",
                 "code": exc.code}), status
        db().expire_all()
        if present.challenge_view(db(), attempt_id, 1) is None:
            nxt = f"/play/attempt/{attempt_id}/debrief"
        else:
            nxt = f"/play/attempt/{attempt_id}/challenge/1"
        return jsonify({"message": "Attempt started.",
                        "attempt_id": attempt_id, "next": nxt})

    @app.route("/api/play/attempt/<int:attempt_id>/challenge/<int:index>",
               methods=["GET"], endpoint="api_play_challenge")
    def api_play_challenge(attempt_id: int, index: int):
        access, denied = _attempt_access(attempt_id, False)
        if denied is not None:
            return denied
        view = present.challenge_view(db(), attempt_id, index)
        if view is None:
            return _err("Unknown challenge", 404)
        return jsonify(
            {"challenge": dict(view, preview=access["preview"])})

    @app.route("/api/play/attempt/<int:attempt_id>/challenge/<int:index>"
               "/answer",
               methods=["POST"], endpoint="api_play_answer")
    def api_play_answer(attempt_id: int, index: int):
        user = current_user()
        if user is None:  # pragma: no cover - _guard answers first
            return _err("Log in first.", 401)
        _, denied = _attempt_access(attempt_id, True)
        if denied is not None:
            return denied
        view = present.challenge_view(db(), attempt_id, index)
        if view is None:
            return _err("Unknown challenge", 404)
        payload = _payload()
        goals = payload.get("goals") or []
        if isinstance(goals, str):
            goals = [goals]
        try:
            answer_challenge(
                app.config["make_session"], attempt_id, user["id"],
                view["challenge_version_id"],
                [str(key) for key in goals],
                note=payload.get("note") or "")
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify(
                {"error": f"Answer rejected ({exc.code}): {exc}",
                 "code": exc.code}), status
        if index < view["total"]:
            nxt = f"/play/attempt/{attempt_id}/challenge/{index + 1}"
        else:
            nxt = f"/play/attempt/{attempt_id}/debrief"
        return jsonify({"message": "Answer recorded.", "next": nxt})

    @app.route("/api/play/attempt/<int:attempt_id>/events",
               methods=["POST"], endpoint="api_play_events")
    def api_play_events(attempt_id: int):
        user = current_user()
        if user is None:  # pragma: no cover - _guard answers first
            return _err("Log in first.", 401)
        _, denied = _attempt_access(attempt_id, True)
        if denied is not None:
            return denied
        payload = _payload()
        client_event_id = payload.get("client_event_id", "")
        verb = payload.get("verb", "")
        if (not isinstance(client_event_id, str) or not client_event_id.strip()
                or len(client_event_id) > 100):
            return _err("Event rejected (invalid_event): "
                        "client_event_id must be 1-100 characters.",
                        400)
        if not isinstance(verb, str) or not verb.strip():
            return _err("Event rejected (invalid_event): "
                        "verb must be a non-blank string.", 400)
        extras = payload.get("payload", {})
        if not isinstance(extras, dict):
            return _err("Event rejected (invalid_event): "
                        "payload must be an object.", 400)
        for field in ("object_type", "object_ref"):
            if field in payload and not isinstance(payload[field], str):
                return _err(f"Event rejected (invalid_event): "
                            f"{field} must be a string.", 400)
        try:
            event_id, duplicate = record_client_event(
                app.config["make_session"], attempt_id, user["id"],
                client_event_id.strip(), verb,
                object_type=payload.get("object_type", "") or "",
                object_ref=payload.get("object_ref", "") or "",
                payload=dict(extras))
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify(
                {"error": f"Event rejected ({exc.code}): {exc}",
                 "code": exc.code}), status
        return jsonify({
            "message": ("Event already recorded." if duplicate
                        else "Event recorded."),
            "event_id": event_id,
            "duplicate": duplicate,
        })

    @app.route("/api/play/attempt/<int:attempt_id>/checkpoints",
               methods=["POST"], endpoint="api_play_checkpoint_save")
    def api_play_checkpoint_save(attempt_id: int):
        user = current_user()
        if user is None:  # pragma: no cover - _guard answers first
            return _err("Log in first.", 401)
        _, denied = _attempt_access(attempt_id, True)
        if denied is not None:
            return denied
        payload = _payload()
        try:
            stage_version_id = int(payload.get("stage_version_id"))
        except (TypeError, ValueError):
            return _err("Checkpoint rejected (invalid_checkpoint): "
                        "stage_version_id must be an integer.", 400)
        state = payload.get("state", {})
        if not isinstance(state, dict):
            return _err("Checkpoint rejected (invalid_checkpoint): "
                        "state must be an object.", 400)
        try:
            checkpoint_id, sequence_no = save_checkpoint(
                app.config["make_session"], attempt_id, user["id"],
                stage_version_id, dict(state))
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify(
                {"error": f"Checkpoint rejected ({exc.code}): {exc}",
                 "code": exc.code}), status
        return jsonify({
            "message": "Checkpoint recorded.",
            "checkpoint_id": checkpoint_id,
            "checkpoint_sequence": sequence_no,
        })

    @app.route("/api/play/attempt/<int:attempt_id>/checkpoints/latest",
               methods=["GET"], endpoint="api_play_checkpoint_latest")
    def api_play_checkpoint_latest(attempt_id: int):
        user = current_user()
        if user is None:  # pragma: no cover - _guard answers first
            return _err("Log in first.", 401)
        access, denied = _attempt_access(attempt_id, False)
        if denied is not None:
            return denied
        try:
            found = latest_checkpoint(
                app.config["make_session"], attempt_id,
                user["id"] if not access["preview"]
                else present.attempt_owner(db(), attempt_id))
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify(
                {"error": f"Checkpoint rejected ({exc.code}): {exc}",
                 "code": exc.code}), status
        if found is None:
            return _err("No checkpoints yet.", 404)
        return jsonify({"checkpoint": dict(found, preview=access["preview"])})

    @app.route("/api/play/attempt/<int:attempt_id>/debrief",
               methods=["GET"], endpoint="api_play_debrief")
    def api_play_debrief(attempt_id: int):
        access, denied = _attempt_access(attempt_id, False)
        if denied is not None:
            return denied
        view = present.debrief_view(db(), attempt_id)
        return jsonify(
            {"debrief": dict(view, preview=access["preview"])})

    @app.route("/api/play/attempt/<int:attempt_id>/rate",
               methods=["POST"], endpoint="api_play_rate")
    def api_play_rate(attempt_id: int):
        user = current_user()
        if user is None:  # pragma: no cover - _guard answers first
            return _err("Log in first.", 401)
        _, denied = _attempt_access(attempt_id, True)
        if denied is not None:
            return denied
        try:
            score = int(_payload().get("score", 0))
        except (TypeError, ValueError):
            score = 0
        try:
            rate_lesson(app.config["make_session"], attempt_id,
                        user["id"], score)
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify(
                {"error": f"Rating rejected ({exc.code}): {exc}",
                 "code": exc.code}), status
        return jsonify({"message": "Rating recorded.",
                        "debrief": _debrief(attempt_id)})

    @app.route("/api/play/attempt/<int:attempt_id>/finish",
               methods=["POST"], endpoint="api_play_finish")
    def api_play_finish(attempt_id: int):
        user = current_user()
        if user is None:  # pragma: no cover - _guard answers first
            return _err("Log in first.", 401)
        _, denied = _attempt_access(attempt_id, True)
        if denied is not None:
            return denied
        try:
            finish_attempt(
                app.config["make_session"], attempt_id, user["id"])
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify(
                {"error": f"Finish rejected ({exc.code}): {exc}",
                 "code": exc.code}), status
        return jsonify({"message": "Attempt finished.",
                        "debrief": _debrief(attempt_id)})

    @app.route("/api/play/attempt/<int:attempt_id>/retry",
               methods=["POST"], endpoint="api_play_retry")
    def api_play_retry(attempt_id: int):
        user = current_user()
        if user is None:  # pragma: no cover - _guard answers first
            return _err("Log in first.", 401)
        _, denied = _attempt_access(attempt_id, True)
        if denied is not None:
            return denied
        try:
            new_id = retry_attempt(
                app.config["make_session"], attempt_id, user["id"])
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify(
                {"error": f"Retry rejected ({exc.code}): {exc}",
                 "code": exc.code}), status
        db().expire_all()
        if present.challenge_view(db(), new_id, 1) is None:
            nxt = f"/play/attempt/{new_id}/debrief"
        else:
            nxt = f"/play/attempt/{new_id}/challenge/1"
        return jsonify({"message": "Retry started.",
                        "attempt_id": new_id, "next": nxt})

    @app.route("/api/verdicts/<int:event_id>/override", methods=["POST"],
               endpoint="api_verdict_override")
    def api_verdict_override(event_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        payload = _payload()
        try:
            record_verdict_override(
                app.config["make_session"], event_id, _actor_id(),
                reason=payload.get("reason") or "",
                corrected_passed=payload.get("corrected") == "pass",
                corrected_score=_score(payload.get("score", "")),
            )
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify(
                {"error": f"Override rejected ({exc.code}): {exc}",
                 "code": exc.code}), status
        return jsonify({"message": "Override recorded.",
                        "progress": _progress_for_event(event_id)})

    @app.route("/api/attempts/<int:attempt_id>/flag", methods=["POST"],
               endpoint="api_attempt_flag")
    def api_attempt_flag(attempt_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        payload = _payload()
        try:
            flag_misconception(
                app.config["make_session"], attempt_id, _actor_id(),
                misconception_id=_flag_misconception_id(
                    payload.get("misconception_id")),
                note=payload.get("note") or "",
            )
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify(
                {"error": f"Flag rejected ({exc.code}): {exc}",
                 "code": exc.code}), status
        return jsonify({"message": "Flag recorded.",
                        "progress": _progress_for_attempt(attempt_id)})

    @app.route("/api/attempts/<int:attempt_id>/teacher-evaluations",
               methods=["POST"], endpoint="api_teacher_evaluation")
    def api_teacher_evaluation(attempt_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        payload = _payload()
        try:
            event_id = record_teacher_evaluation(
                app.config["make_session"], attempt_id,
                payload.get("goal_id"), _actor_id(),
                payload.get("passed"),
                rationale=payload.get("rationale") or "",
            )
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify(
                {"error": f"Evaluation rejected ({exc.code}): {exc}",
                 "code": exc.code}), status
        return jsonify({"message": "Evaluation recorded.",
                        "event_id": event_id})

    @app.route("/api/lessons/<int:lesson_id>/brief", methods=["GET"],
               endpoint="api_brief_context")
    def api_brief_context(lesson_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        ctx = present.brief_context(db(), lesson_id)
        if ctx is None:
            return _err("Unknown lesson", 404)
        return jsonify({"brief": ctx})

    @app.route("/api/lessons/<int:lesson_id>/brief", methods=["POST"],
               endpoint="api_brief_submit")
    def api_brief_submit(lesson_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        payload = _payload()
        include = _brief_items(payload.get("must_include", ""))
        avoid = _brief_items(payload.get("must_avoid", ""))
        constraints: dict[str, list[str]] = {}
        if include:
            constraints["must_include"] = include
        if avoid:
            constraints["must_avoid"] = avoid
        try:
            result = submit_brief(
                app.config["make_session"],
                lesson_id=lesson_id,
                actor_id=_actor_id(),
                objectives=_brief_lines(payload.get("objectives", "")),
                mental_models=_brief_lines(
                    payload.get("mental_models", "")),
                focus=payload.get("focus", "") or "",
                constraints=constraints,
                priority=_brief_priority(payload.get("priority", 1)),
                student_id=_brief_student_id(payload.get("student_id")),
            )
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify({"error": f"Brief rejected ({exc.code}): {exc}",
                            "code": exc.code}), status
        return jsonify({"message": "Brief recorded.",
                        "version_id": result.lesson_version_id,
                        "dossier": _dossier("lesson",
                                            result.lesson_version_id)})

    @app.route("/api/lessons/<int:lesson_id>/directives", methods=["GET"],
               endpoint="api_directives_panel")
    def api_directives_panel(lesson_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        panel = present.brief_context(db(), lesson_id)
        if panel is None:
            return _err("Unknown lesson", 404)
        return jsonify({"panel": panel})

    @app.route("/api/lessons/<int:lesson_id>/directives", methods=["POST"],
               endpoint="api_directives_create")
    def api_directives_create(lesson_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        payload = _payload()
        include = _brief_items(payload.get("must_include", ""))
        avoid = _brief_items(payload.get("must_avoid", ""))
        constraints: dict[str, list[str]] = {}
        if include:
            constraints["must_include"] = include
        if avoid:
            constraints["must_avoid"] = avoid
        try:
            directive_id = create_steer_directive(
                app.config["make_session"],
                lesson_id=lesson_id,
                actor_id=_actor_id(),
                focus=payload.get("focus", "") or "",
                constraints=constraints,
                priority=_brief_priority(payload.get("priority", 1)),
                student_id=_brief_student_id(payload.get("student_id")),
            )
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify(
                {"error": f"Directive rejected ({exc.code}): {exc}",
                 "code": exc.code}), status
        return jsonify({"message": "Directive recorded.",
                        "directive_id": directive_id,
                        "panel": _panel(lesson_id)})

    @app.route("/api/directives/<int:directive_id>/deactivate",
               methods=["POST"], endpoint="api_directives_deactivate")
    def api_directives_deactivate(directive_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        detail = present.directive_detail(db(), directive_id)
        if detail is None:
            return _err("Unknown directive", 404)
        try:
            deactivate_directive(
                app.config["make_session"], directive_id, _actor_id())
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify(
                {"error": f"Directive rejected ({exc.code}): {exc}",
                 "code": exc.code}), status
        return jsonify({"message": "Directive deactivated.",
                        "panel": _panel(detail["lesson_id"])})

    @app.route("/api/directives/<int:directive_id>", methods=["GET"],
               endpoint="api_directive_detail")
    def api_directive_detail(directive_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        detail = present.directive_detail(db(), directive_id)
        if detail is None:
            return _err("Unknown directive", 404)
        return jsonify({"directive": detail})

    @app.route("/api/directives/<int:directive_id>/edit", methods=["POST"],
               endpoint="api_directive_edit")
    def api_directive_edit(directive_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        detail = present.directive_detail(db(), directive_id)
        if detail is None:
            return _err("Unknown directive", 404)
        payload = _payload()
        constraints = None
        if "must_include" in payload or "must_avoid" in payload:
            built: dict[str, list[str]] = {}
            include = _brief_items(payload.get("must_include", ""))
            avoid = _brief_items(payload.get("must_avoid", ""))
            if include:
                built["must_include"] = include
            if avoid:
                built["must_avoid"] = avoid
            constraints = built
        try:
            update_directive(
                app.config["make_session"], directive_id, _actor_id(),
                focus=payload.get("focus"),
                constraints=constraints,
                priority=(_brief_priority(payload.get("priority"))
                          if "priority" in payload else None),
            )
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify(
                {"error": f"Directive rejected ({exc.code}): {exc}",
                 "code": exc.code}), status
        db().expire_all()
        return jsonify({"message": "Directive updated.",
                        "directive": present.directive_detail(
                            db(), directive_id)})

    def _panel(lesson_id: int):
        """Fresh panel read (the g-scoped session may predate a write)."""
        db().expire_all()
        return present.brief_context(db(), lesson_id)

    def _debrief(attempt_id: int):
        """Fresh owner debrief (the g-scoped session may predate a write)."""
        db().expire_all()
        return dict(present.debrief_view(db(), attempt_id), preview=False)

    def _assignment_id(value) -> int | None:
        """Assign-form id selector: blank or garbage means unset."""
        if isinstance(value, int):
            return value
        if value is None:
            return None
        raw = str(value).strip()
        return int(raw) if raw.isdigit() else None

    def _assignments_payload():
        """Fresh list + options (the g-scoped session may predate a write)."""
        db().expire_all()
        return {"assignments": present.assignment_list(db()),
                "options": present.assignment_options(db())}

    def _score(value) -> float | None:
        """Optional 0–1 score field; blank or garbage means no score."""
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value or "").strip())
        except ValueError:
            return None

    def _flag_misconception_id(value) -> int | None:
        """Flag-form selector: blank or garbage means a general note."""
        if isinstance(value, int):
            return value
        if value is None:
            return None
        raw = str(value).strip()
        return int(raw) if raw.isdigit() else None

    def _progress_for_event(event_id: int):
        """Fresh progress for the event's assignment (post-write read)."""
        db().expire_all()
        event = db().get(ExperienceEvent, event_id)
        return present.assignment_progress(db(), event.attempt.assignment_id)

    def _progress_for_attempt(attempt_id: int):
        """Fresh progress for the attempt's assignment (post-write read)."""
        db().expire_all()
        attempt = db().get(Attempt, attempt_id)
        return present.assignment_progress(db(), attempt.assignment_id)

    def _admin():
        """Current admin user, or a JSON error response when forbidden."""
        user = current_user()
        if user is None:  # pragma: no cover - _guard answers first
            return None, _err("Log in first.", 401)
        if user["role"] != "admin":
            return None, _err("This area is for school admins.", 403)
        return user, None

    def _audit_actor(value) -> int | None:
        """Actor filter selector: blank or garbage means everyone."""
        if isinstance(value, int):
            return value
        if value is None:
            return None
        raw = str(value).strip()
        return int(raw) if raw.isdigit() else None

    def _audit_date(value):
        """YYYY-MM-DD filter value, or None when blank or invalid."""
        import datetime as _dt

        try:
            return _dt.date.fromisoformat(str(value or "").strip())
        except ValueError:
            return None

    def _staff():
        """Current staff user, or a JSON error response when forbidden."""
        user = current_user()
        if user is None:  # pragma: no cover - _guard answers first
            return None, _err("Log in first.", 401)
        if user["role"] not in ("teacher", "admin"):
            return None, _err("This area is for teachers and admins.", 403)
        return user, None

    def _attempt_access(attempt_id: int, mutate: bool):
        """Attempt access as JSON: owner always, teachers read-only."""
        user = current_user()
        if user is None:  # pragma: no cover - _guard answers first
            return None, _err("Log in first.", 401)
        owner = present.attempt_owner(db(), attempt_id)
        if owner is None:
            return None, _err("Unknown attempt", 404)
        if user["id"] == owner:
            return {"preview": False}, None
        if not mutate and user["role"] in ("teacher", "admin"):
            return {"preview": True}, None
        return None, _err(
            "This attempt belongs to another student.", 403)

    def _dossier(kind: str, version_id: int):
        """Fresh dossier read (the g-scoped session may predate a write)."""
        db().expire_all()
        return present.detail(db(), kind, version_id)

    def _payload() -> dict:
        body = request.get_json(silent=True)
        if isinstance(body, dict):
            return body
        return dict(request.form)

    def _actor_id() -> int:
        return flask_session["actor_id"]

    def _run(action: str, kind: str, version_id: int, fn):
        """Run a review action, returning message + refreshed dossier."""
        if kind not in present.KINDS:
            return _err("Unknown level", 404)
        try:
            fn()
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify({"error": f"{action} rejected ({exc.code}): {exc}",
                            "code": exc.code}), status
        return jsonify({"message": f"{action} recorded.",
                        "dossier": _dossier(kind, version_id)})

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

    @app.route("/api/review/<kind>/<int:version_id>", methods=["GET"],
               endpoint="api_review_dossier")
    def api_review_dossier(kind: str, version_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        if kind not in present.KINDS:
            return _err("Unknown level", 404)
        dossier = _dossier(kind, version_id)
        if dossier is None:
            return _err("Unknown version", 404)
        return jsonify({"dossier": dossier})

    @app.route("/api/review/<kind>/<int:version_id>/approve",
               methods=["POST"], endpoint="api_review_approve")
    def api_review_approve(kind: str, version_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        rationale = _payload().get("rationale", "")
        return _run("Approval", kind, version_id, lambda: record_approval(
            app.config["make_session"], kind, version_id, _actor_id(),
            Decision.approved, rationale))

    @app.route("/api/review/<kind>/<int:version_id>/reject",
               methods=["POST"], endpoint="api_review_reject")
    def api_review_reject(kind: str, version_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        rationale = _payload().get("rationale", "")
        return _run("Rejection", kind, version_id, lambda: record_approval(
            app.config["make_session"], kind, version_id, _actor_id(),
            Decision.rejected, rationale))

    @app.route("/api/review/<kind>/<int:version_id>/edit",
               methods=["POST"], endpoint="api_review_edit")
    def api_review_edit(kind: str, version_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        payload = _payload()
        content_ref = (payload.get("content_ref") or None
                       if kind == "asset" else None)
        uses = payload.get("uses") if kind == "stage" else None
        pins = payload.get("pins") if kind == "lesson" else None

        def _edit():
            make = app.config["make_session"]
            actor = _actor_id()
            # Structure first: its guards subsume the rationale
            # write's, so a rejection leaves nothing half-applied.
            if uses is not None:
                update_stage_uses(make, version_id, actor, uses)
            if pins is not None:
                update_lesson_composition(make, version_id, actor, pins)
            update_draft(
                make, kind, version_id, actor,
                rationale=payload.get("rationale"),
                content_ref=content_ref)

        return _run("Edit", kind, version_id, _edit)

    @app.route("/api/review/<kind>/<int:version_id>/publish",
               methods=["POST"], endpoint="api_review_publish")
    def api_review_publish(kind: str, version_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        rationale = _payload().get("rationale", "")
        extra = {"finalize_preview": finalize_preview} if kind in (
            "asset", "stage") else {}
        return _run("Publication", kind, version_id,
                    lambda: _PUBLISH[kind](
                        app.config["make_session"], version_id, _actor_id(),
                        rationale, **extra))

    @app.route("/api/review/<kind>/<int:version_id>/rollback",
               methods=["POST"], endpoint="api_review_rollback")
    def api_review_rollback(kind: str, version_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        rationale = _payload().get("rationale", "")
        return _run("Rollback", kind, version_id,
                    lambda: _ROLLBACK[kind](
                        app.config["make_session"], version_id, _actor_id(),
                        rationale))

    @app.route("/api/review/<kind>/<int:version_id>/retire",
               methods=["POST"], endpoint="api_review_retire")
    def api_review_retire(kind: str, version_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        rationale = _payload().get("rationale", "")
        return _run("Retirement", kind, version_id,
                    lambda: _RETIRE[kind](
                        app.config["make_session"], version_id, _actor_id(),
                        rationale))

    @app.route("/api/review/asset/<int:version_id>/revise",
               methods=["POST"], endpoint="api_review_revise")
    def api_review_revise(version_id: int):
        _, denied = _staff()
        if denied is not None:
            return denied
        rationale = _payload().get("rationale", "")
        try:
            new_id = revise_asset_version(
                app.config["make_session"], version_id, _actor_id(),
                rationale)
        except PublicationError as exc:
            status = {"not_found": 404, "forbidden": 403}.get(exc.code, 400)
            return jsonify({"error": f"Revision rejected ({exc.code}): {exc}",
                            "code": exc.code}), status
        return jsonify({"message": "Revision drafted.",
                        "version_id": new_id,
                        "dossier": _dossier("asset", new_id)})
