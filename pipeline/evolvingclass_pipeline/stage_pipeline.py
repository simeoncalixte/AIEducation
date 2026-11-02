"""Stage proposal orchestration: run lifecycle around template assembly."""

from __future__ import annotations

from evolvingclass_pipeline.domain import (
    GenerationFailed,
    StageAssemblyRequest,
    StageProposalResult,
)
from evolvingclass_pipeline.ports import RunStore, StageBackend, StageLibraryPort

PROMPT_REF = "stage-assemble/v1"
POLICY_VERSION = "policy/v1"


class StagePipeline:
    """Assemble a stage draft proposal, recording the run either way."""

    def __init__(self, library: StageLibraryPort, backend: StageBackend,
                 runs: RunStore) -> None:
        self._library = library
        self._backend = backend
        self._runs = runs

    def propose(self, request: StageAssemblyRequest,
              created_by_id: int) -> StageProposalResult:
        run_id = self._runs.begin_run(
            self._backend.agent_ref, self._backend.model_ref, PROMPT_REF,
            {"lesson_id": request.lesson_id, "title": request.title,
             "asset_version_ids": list(request.asset_version_ids)},
            POLICY_VERSION,
        )
        self._runs.mark_running(run_id)
        try:
            assembly = self._backend.assemble(request)
            ref = self._library.save_stage_draft(
                assembly, request.directives, created_by_id, run_id
            )
        except Exception as exc:
            self._runs.mark_failed(run_id, f"{type(exc).__name__}: {exc}")
            raise
        self._runs.mark_completed(run_id)
        return StageProposalResult(
            reused=False, stage_id=ref.stage_id, version_id=ref.version_id,
            version_no=ref.version_no, run_id=run_id,
        )
