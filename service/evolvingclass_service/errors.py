"""Errors for the EvolvingClass service layer."""

from __future__ import annotations


class PublicationError(Exception):
    """Raised when a publication transaction is rejected.

    Attributes:
        code: Stable machine-readable reason, suitable for API mapping.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


NOT_FOUND = "not_found"
NOT_DRAFT = "not_draft"
NOT_PUBLISHED = "not_published"
NOT_RETIRED = "not_retired"
NOTHING_LIVE = "nothing_live"
NOT_APPROVED = "not_approved"
FORBIDDEN = "forbidden"
EMPTY_COMPOSITION = "empty_composition"
UNPUBLISHED_DEPENDENCY = "unpublished_dependency"
MISSING_GOALS = "missing_goals"
INVALID_BRIEF = "invalid_brief"
INVALID_DIRECTIVE = "invalid_directive"
INVALID_SCOPE = "invalid_scope"
INVALID_FEEDBACK = "invalid_feedback"
INVALID_PLAY = "invalid_play"
