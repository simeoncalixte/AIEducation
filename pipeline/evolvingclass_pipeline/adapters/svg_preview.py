"""Deterministic SVG posters: lightweight stills, zero GPU.

Posters render one frame; turntables render a four-panel strip. Bytes are
stable for identical input (no timestamps), so tests assert exact output and
reviewers can diff renders.
"""

from __future__ import annotations

import html
from pathlib import Path

from evolvingclass_pipeline.domain import PreviewRequest, PreviewResult
from evolvingclass_pipeline.ports import PreviewPort

_PANELS = ("front", "side", "top", "detail")


class SvgPreviewRenderer(PreviewPort):
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def render(self, request: PreviewRequest) -> PreviewResult:
        if request.kind == "turntable":
            svg = self._strip(request)
            name = f"v{request.version_no}_turntable.svg"
        else:
            svg = self._poster(request, "front")
            name = f"v{request.version_no}_poster.svg"
        scope = self._root / request.namespace if request.namespace else self._root
        path = scope / str(request.asset_id) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg)
        ref = f"{request.asset_id}/{name}"
        if request.namespace:
            ref = f"{request.namespace}/{ref}"
        return PreviewResult(storage_ref=ref)

    @staticmethod
    def _poster(request: PreviewRequest, view: str) -> str:
        title = html.escape(request.title)
        kind = html.escape(request.metadata.get("asset_kind", ""))
        objectives = "".join(
            f"<text x='20' y='{120 + i * 22}' font-size='14'>{html.escape(o)}</text>"
            for i, o in enumerate(request.metadata.get("objectives", [])[:4])
        )
        return (
            f"<svg xmlns='http://www.w3.org/2000/svg' width='480' height='270'>"
            f"<rect width='480' height='270' fill='#1b2430'/>"
            f"<text x='20' y='50' font-size='24' fill='#ffffff'>{title}</text>"
            f"<text x='20' y='80' font-size='14' fill='#9fb2cc'>{kind} · "
            f"v{request.version_no} · {view}</text>{objectives}</svg>"
        )

    @classmethod
    def _strip(cls, request: PreviewRequest) -> str:
        panels = "".join(
            f"<g transform='translate({i * 480},0)'>"
            f"{cls._poster(request, view)}</g>"
            for i, view in enumerate(_PANELS)
        )
        return (
            f"<svg xmlns='http://www.w3.org/2000/svg' width='1920' height='270'>"
            f"{panels}</svg>"
        )
