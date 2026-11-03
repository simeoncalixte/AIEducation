"""EvolvingClass service layer: transactional application services."""

from .assignments import assign_lesson
from .briefing import BriefResult, submit_brief
from .directives import (
    create_steer_directive,
    deactivate_directive,
    update_directive,
)
from .errors import PublicationError
from .feedback import (
    flag_misconception,
    record_teacher_evaluation,
    record_verdict_override,
)
from .goals import evaluate_attempt
from .launch import (
    decide_launch,
    list_launch_decisions,
    match_capabilities,
    register_device,
    report_device_capabilities,
)
from .play import (
    answer_challenge,
    finish_attempt,
    latest_checkpoint,
    rate_lesson,
    record_client_event,
    retry_attempt,
    save_checkpoint,
    start_attempt,
)
from .publication import (
    PreviewFinalizer,
    ensure_draft,
    publish_asset_version,
    publish_lesson_version,
    publish_stage_version,
    resolve_current_lesson_version,
    retire_asset_version,
    retire_lesson_version,
    retire_stage_version,
    rollback_asset_version,
    rollback_lesson_version,
    rollback_stage_version,
)
from .review import (
    record_approval,
    revise_asset_version,
    update_draft,
    update_lesson_composition,
    update_stage_uses,
)

__all__ = [
    "BriefResult",
    "PreviewFinalizer",
    "PublicationError",
    "assign_lesson",
    "create_steer_directive",
    "deactivate_directive",
    "decide_launch",
    "answer_challenge",
    "ensure_draft",
    "evaluate_attempt",
    "finish_attempt",
    "flag_misconception",
    "latest_checkpoint",
    "list_launch_decisions",
    "match_capabilities",
    "rate_lesson",
    "record_client_event",
    "register_device",
    "report_device_capabilities",
    "record_teacher_evaluation",
    "record_verdict_override",
    "retry_attempt",
    "revise_asset_version",
    "save_checkpoint",
    "start_attempt",
    "submit_brief",
    "update_directive",
    "record_approval",
    "update_draft",
    "update_lesson_composition",
    "update_stage_uses",
    "publish_asset_version",
    "publish_lesson_version",
    "publish_stage_version",
    "resolve_current_lesson_version",
    "retire_asset_version",
    "retire_lesson_version",
    "retire_stage_version",
    "rollback_asset_version",
    "rollback_lesson_version",
    "rollback_stage_version",
]
