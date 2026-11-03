"""Scene launch matching: capabilities vs requirements (SCRUM-39).

Before an immersive stage launches, its scene requirements are
checked against the device's reported capabilities. Devices that
meet every required capability route immersive; missing required
capabilities route to the web fallback with a reason. Preferred
(matching ``required=False``) capabilities only degrade gracefully.
Every routing decision is logged as a server ``launch-decision``
event on the attempt, so each launch carries its own audit trail.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from collections.abc import Collection, Iterable, Mapping

from sqlalchemy import func, select

from DataModels import (
    AppUser,
    Attempt,
    Device,
    DeviceCapability,
    EventOrigin,
    ExperienceEvent,
    SceneRequirement,
    StageVersion,
    UserRole,
)

from .errors import (
    FORBIDDEN,
    INVALID_PLAY,
    NOT_FOUND,
    PublicationError,
)
from .publication import SessionFactory

LAUNCH_VERB = "launch-decision"
ROUTE_IMMERSIVE = "immersive"
ROUTE_WEB = "web"


def match_capabilities(
    reported: Collection[str],
    required: Iterable[str],
    preferred: Iterable[str],
) -> dict[str, list[str]]:
    """Compare reported capabilities against requirement lists.

    Returns the missing required and preferred capabilities, sorted
    for deterministic reasons and payloads.
    """
    have = set(reported)
    return {
        "missing_required": sorted(set(required) - have),
        "missing_preferred": sorted(set(preferred) - have),
    }


def _require_student(session, student_id: int) -> AppUser:
    student = session.get(AppUser, student_id)
    if student is None:
        raise PublicationError(NOT_FOUND, f"Unknown student {student_id}.")
    if student.role is not UserRole.student:
        raise PublicationError(
            FORBIDDEN, "Only students launch stages on a device.")
    return student


def _require_owner(session, attempt_id: int, student_id: int) -> Attempt:
    attempt = session.get(Attempt, attempt_id)
    if attempt is None:
        raise PublicationError(NOT_FOUND, f"Unknown attempt {attempt_id}.")
    if attempt.student_id != student_id:
        raise PublicationError(
            FORBIDDEN, "An attempt belongs to its student.")
    return attempt


def _require_device(session, device_id: int, student_id: int) -> Device:
    device = session.get(Device, device_id)
    if device is None:
        raise PublicationError(NOT_FOUND, f"Unknown device {device_id}.")
    if device.student_id != student_id:
        raise PublicationError(
            FORBIDDEN, "A device belongs to its student.")
    return device


def _clean_capabilities(capabilities) -> list[str]:
    """Normalize inline capability reports to stripped key strings."""
    cleaned: list[str] = []
    for entry in capabilities:
        if isinstance(entry, Mapping):
            entry = entry.get("capability", "")
        if not isinstance(entry, str) or not entry.strip():
            raise PublicationError(
                INVALID_PLAY,
                "Reported capabilities must be non-blank strings.")
        cleaned.append(entry.strip())
    return cleaned


def register_device(
    make_session: SessionFactory,
    student_id: int,
    label: str,
) -> int:
    """Register a student device for capability reporting."""
    if not label.strip():
        raise PublicationError(
            INVALID_PLAY, "A device needs a label.")
    with make_session() as session, session.begin():
        _require_student(session, student_id)
        device = Device(student_id=student_id, label=label.strip())
        session.add(device)
        session.flush()
        assert device.id is not None
        return device.id


def report_device_capabilities(
    make_session: SessionFactory,
    device_id: int,
    student_id: int,
    capabilities: list,
) -> list[str]:
    """Upsert reported capabilities on a device; returns sorted keys.

    Entries are capability strings or ``{"capability", "detail"}``
    mappings; re-reports overwrite the detail and the report time.
    """
    cleaned = _clean_capabilities(capabilities)
    details = {
        entry["capability"].strip(): (entry.get("detail") or None)
        for entry in capabilities
        if isinstance(entry, Mapping)
    }
    with make_session() as session, session.begin():
        device = _require_device(session, device_id, student_id)
        known = {cap.capability: cap for cap in device.capabilities}
        for key in cleaned:
            row = known.get(key)
            if row is None:
                row = DeviceCapability(device_id=device.id,
                                       capability=key)
                session.add(row)
                known[key] = row
            if key in details:
                row.detail = details[key]
            row.reported_at = _dt.datetime.now(_dt.timezone.utc)
        return sorted(known)


def decide_launch(
    make_session: SessionFactory,
    attempt_id: int,
    student_id: int,
    stage_version_id: int,
    capabilities: list | None = None,
    device_id: int | None = None,
) -> dict:
    """Route one launch and log the decision on the attempt.

    Capabilities come from the inline report, the device's stored
    report, or both (unioned). Returns the route (``immersive`` or
    ``web``), the reason, the missing lists, and the log event id.
    """
    if capabilities is None and device_id is None:
        raise PublicationError(
            INVALID_PLAY,
            "A launch needs reported capabilities or a device.")
    inline = _clean_capabilities(capabilities or [])
    with make_session() as session, session.begin():
        attempt = _require_owner(session, attempt_id, student_id)
        stage_version = session.get(StageVersion, stage_version_id)
        if stage_version is None:
            raise PublicationError(
                NOT_FOUND, f"Unknown stage version {stage_version_id}.")
        pinned = {pin.stage_version_id for pin in attempt.pins}
        if stage_version_id not in pinned:
            raise PublicationError(
                INVALID_PLAY,
                "That stage version is not pinned to this attempt.")
        reported = set(inline)
        if device_id is not None:
            device = _require_device(session, device_id, student_id)
            reported.update(cap.capability for cap in device.capabilities)
        required = [
            req.capability for req in stage_version.scene_requirements
            if req.required
        ]
        preferred = [
            req.capability for req in stage_version.scene_requirements
            if not req.required
        ]
        missing = match_capabilities(reported, required, preferred)
        if missing["missing_required"]:
            route = ROUTE_WEB
            reason = ("Missing required capabilities: "
                      + ", ".join(missing["missing_required"])
                      + "; routed to the web fallback.")
        elif missing["missing_preferred"]:
            route = ROUTE_IMMERSIVE
            reason = ("Immersive with degraded capabilities: "
                      + ", ".join(missing["missing_preferred"]) + ".")
        elif required or preferred:
            route = ROUTE_IMMERSIVE
            reason = "All scene requirements met."
        else:
            route = ROUTE_IMMERSIVE
            reason = "No scene requirements declared."
        sequence_no = (session.scalar(
            select(func.max(ExperienceEvent.sequence_no)).where(
                ExperienceEvent.attempt_id == attempt_id)
        ) or 0) + 1
        event = ExperienceEvent(
            attempt_id=attempt_id,
            client_event_id=f"launch-{uuid.uuid4().hex[:12]}",
            sequence_no=sequence_no,
            origin=EventOrigin.server,
            device_id=device_id,
            actor_id=student_id,
            verb=LAUNCH_VERB,
            object_type="stage",
            object_ref=str(stage_version_id),
            stage_version_id=stage_version_id,
            payload={
                "route": route,
                "reason": reason,
                "missing_required": missing["missing_required"],
                "missing_preferred": missing["missing_preferred"],
                "reported": sorted(reported),
                "required": sorted(required),
                "preferred": sorted(preferred),
            },
        )
        session.add(event)
        session.flush()
        assert event.id is not None
        return {
            "route": route,
            "reason": reason,
            "missing_required": missing["missing_required"],
            "missing_preferred": missing["missing_preferred"],
            "stage_version_id": stage_version_id,
            "device_id": device_id,
            "event_id": event.id,
        }


def list_launch_decisions(
    make_session: SessionFactory,
    attempt_id: int,
    student_id: int,
) -> list[dict]:
    """Logged routing decisions for an attempt, in launch order."""
    with make_session() as session:
        _require_owner(session, attempt_id, student_id)
        rows = list(session.scalars(
            select(ExperienceEvent)
            .where(
                ExperienceEvent.attempt_id == attempt_id,
                ExperienceEvent.origin == EventOrigin.server,
                ExperienceEvent.verb == LAUNCH_VERB,
            )
            .order_by(ExperienceEvent.sequence_no)
        ))
        return [
            {
                "event_id": row.id,
                "sequence_no": row.sequence_no,
                "stage_version_id": row.stage_version_id,
                "device_id": row.device_id,
                "route": row.payload.get("route"),
                "reason": row.payload.get("reason"),
                "missing_required": row.payload.get(
                    "missing_required", []),
                "missing_preferred": row.payload.get(
                    "missing_preferred", []),
            }
            for row in rows
        ]


__all__ = [
    "LAUNCH_VERB",
    "ROUTE_IMMERSIVE",
    "ROUTE_WEB",
    "decide_launch",
    "list_launch_decisions",
    "match_capabilities",
    "register_device",
    "report_device_capabilities",
]
