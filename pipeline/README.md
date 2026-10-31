# Asset generation pipeline

Pilot slice of the generation plane: turn a teacher brief plus directives
into versioned, reviewable asset drafts — or reuse a library match.

## Boundary map

```text
domain.py      pure value objects (frozen, typed, no I/O)
ports.py       abstract boundaries the pipeline depends on (DIP)
asset_pipeline.py  orchestrator: library-first flow + run lifecycle
policy.py      pure content-validation rules (no I/O)
agents/        GenerationBackend implementations (template now, LLM later)
adapters/      I/O implementations (SQLAlchemy, filesystem, SVG previews)
```

Dependency rules (enforced by review, see ticket T3):

- `domain` imports nothing but stdlib.
- `ports` imports `domain` only.
- `asset_pipeline` and `policy` import `domain` + `ports` only.
- `agents/*` implement `ports.GenerationBackend`; no ORM, no filesystem.
- `adapters/*` may import `DataModels`, the filesystem, and third parties.
- Nothing outside `adapters/` imports `DataModels`.

## Data flow (`AssetPipeline.propose`)

1. Open a generation run (`queued` → `running`).
2. Search the library. On a strong match: snapshot directives, complete the
   run, return the reused version (backend never called).
3. Else generate content, validate policy, store the body
   (content-addressed), save the draft version with the directive snapshot,
   render a preview and pin its artifact to the draft, complete the run.
4. Any failure marks the run failed with the error and raises; no draft.

## Running tests

```sh
cd pipeline
PYTHONPATH=/Users/simeon/Projects/EvolvingClass/database \
  ../database/.venv/bin/python -m unittest discover tests
```

(`DataModels` resolves via `PYTHONPATH` until service packaging unifies the
repo into one `src` layout.)
