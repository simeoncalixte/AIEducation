"""Pure content-validation rules. No I/O: trivially testable, safely shared."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from evolvingclass_pipeline.domain import AssetKind, GeneratedContent

# Body field carrying human/AI-readable text per kind, for length caps.
_TEXT_FIELDS: dict[AssetKind, str] = {
    AssetKind.text: "text",
    AssetKind.script: "source",
}


@dataclass(frozen=True)
class ContentPolicy:
    """Pilot content policy.

    - Script bodies may only use allowlisted hooks.
    - Text-bearing bodies respect a length cap.
    - Controlled taxonomies must use vocabulary values (empty vocab
      disables that check).
    """

    allowed_script_hooks: frozenset[str] = frozenset(
        {"on_start", "on_complete", "on_timeout", "on_hint"}
    )
    max_text_chars: int = 20_000
    vocabulary: Mapping[str, frozenset[str]] = field(default_factory=dict)

    def check(self, content: GeneratedContent) -> tuple[str, ...]:
        violations: list[str] = []
        if content.kind is AssetKind.script:
            hooks = content.body.get("hooks", [])
            if not isinstance(hooks, list):
                violations.append("script body must carry a hooks list")
            else:
                unknown = [h for h in hooks if h not in self.allowed_script_hooks]
                if unknown:
                    violations.append(
                        f"script hooks outside allowlist: {sorted(unknown)}"
                    )
        text_field = _TEXT_FIELDS.get(content.kind)
        if text_field is not None:
            text = content.body.get(text_field, "")
            if isinstance(text, str) and len(text) > self.max_text_chars:
                violations.append(
                    f"{text_field} exceeds {self.max_text_chars} chars"
                )
        for taxonomy, allowed in self.vocabulary.items():
            for tag in content.tags:
                if tag.taxonomy == taxonomy and tag.value not in allowed:
                    violations.append(
                        f"tag {taxonomy}:{tag.value} outside vocabulary"
                    )
        return tuple(violations)
