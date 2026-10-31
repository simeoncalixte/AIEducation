"""Orchestrator: library-first proposal flow plus run lifecycle.

Depends on ports + domain only, so tests substitute fakes and production
wires real adapters without changing this file (DIP/OCP).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from evolvingclass_pipeline.domain import (
    GenerationRequest,
    PolicyViolation,
    PreviewRequest,
    ProposalResult,
)
from evolvingclass_pipeline.policy import ContentPolicy
from evolvingclass_pipeline.ports import (
    AssetLibraryPort,
    ContentStore,
    GenerationBackend,
    PreviewPort,
    RunStore,
)


class AssetPipeline:
    def __init__(
        self,
        library: AssetLibraryPort,
        backend: GenerationBackend,
        previews: PreviewPort,
        runs: RunStore,
        store: ContentStore,
        policy: ContentPolicy | None = None,
        *,
        reuse_threshold: float = 0.8,
        prompt_ref: str = "asset-brief/v1",
        policy_version: str = "policy/v1",
    ) -> None:
        self._library = library
        self._backend = backend
        self._previews = previews
        self._runs = runs
        self._store = store
        self._policy = policy or ContentPolicy()
        self._reuse_threshold = reuse_threshold
        self._prompt_ref = prompt_ref
        self._policy_version = policy_version

    def propose(
        self, request: GenerationRequest, created_by_id: int
    ) -> ProposalResult:
        snapshot = self._snapshot(request)
        run_id = self._runs.begin_run(
            agent_ref=self._backend.agent_ref,
            model_ref=self._backend.model_ref,
            prompt_ref=self._prompt_ref,
            params={
                "kind": request.kind.value,
                "title": request.title,
                "parameters": dict(request.parameters),
            },
            policy_version=self._policy_version,
        )
        self._runs.mark_running(run_id)
        try:
            matches = self._library.find_candidates(
                request.kind, request.tags, request.objectives
            )
            if matches and matches[0].score >= self._reuse_threshold:
                best = matches[0]
                preview = self._previews.render(
                    self._preview_for(
                        request, best.asset_id, best.version_id, best.version_no
                    )
                )
                self._runs.mark_completed(run_id)
                return ProposalResult(
                    reused=True,
                    asset_id=best.asset_id,
                    version_id=best.version_id,
                    version_no=best.version_no,
                    run_id=run_id,
                    preview_ref=preview.storage_ref,
                )
            content = self._backend.generate(request)
            violations = self._policy.check(content)
            if violations:
                raise PolicyViolation(violations)
            content = replace(
                content,
                rationale=content.rationale
                + f"\nLibrary miss: no candidate at threshold "
                f"{self._reuse_threshold}; generated new asset.",
            )
            content_ref = self._store.put(content.body)
            ref = self._library.save_draft(
                content, content_ref, snapshot, run_id, created_by_id
            )
            preview_request = self._preview_for(
                request, ref.asset_id, ref.version_id, ref.version_no
            )
            preview = self._previews.render(preview_request)
            self._library.record_preview(
                ref.version_id, preview_request.kind, preview.storage_ref
            )
            self._runs.mark_completed(run_id)
            return ProposalResult(
                reused=False,
                asset_id=ref.asset_id,
                version_id=ref.version_id,
                version_no=ref.version_no,
                run_id=run_id,
                preview_ref=preview.storage_ref,
            )
        except Exception as exc:
            self._runs.mark_failed(run_id, f"{type(exc).__name__}: {exc}")
            raise

    @staticmethod
    def _snapshot(request: GenerationRequest) -> Mapping[str, Any]:
        return {
            "directives": [
                {
                    "id": d.id,
                    "kind": d.kind.value,
                    "focus": d.focus,
                    "constraints": dict(d.constraints),
                    "priority": d.priority,
                }
                for d in sorted(request.directives, key=lambda d: d.id)
            ]
        }

    @staticmethod
    def _preview_for(
        request: GenerationRequest, asset_id: int, version_id: int, version_no: int
    ) -> PreviewRequest:
        return PreviewRequest(
            asset_id=asset_id,
            version_id=version_id,
            version_no=version_no,
            kind="poster",
            title=request.title,
            metadata={
                "asset_kind": request.kind.value,
                "objectives": list(request.objectives),
            },
        )
