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
PYTHONPATH=../database:. ../database/.venv/bin/python -m unittest discover -s tests
```

(`DataModels` resolves via `PYTHONPATH` until service packaging unifies the
repo into one `src` layout.)

## Generation API service (`app.py`)

Composition root that wires the real adapters behind a Flask JSON API so
other applications can use generation without importing the pipeline.
Internal pilot service, no auth.

| Endpoint | Behavior |
|---|---|
| `GET /api/health` | Liveness probe |
| `POST /api/generate/asset` | Run the library-first proposal flow; records the run |
| `POST /api/generate/stage` | Template stage assembly: new stage draft with pinned asset uses; records the run (model-backed authoring stays with SCRUM-30 to SCRUM-34) |
| `POST /api/generate/lesson` | Brief-to-draft composition via `service.submit_brief`; records the run |
| `GET /api/runs[?status=&limit=]` | Run tracking, newest first |
| `GET /api/runs/<id>` | One run, or 404 |

Request shape for asset proposals:

```json
{
  "kind": "text",
  "title": "Gravity",
  "objectives": ["falling bodies"],
  "tags": [{"taxonomy": "subject", "value": "physics"}],
  "directives": [{"id": 11, "kind": "brief", "focus": "intro",
                  "constraints": {}, "priority": 1}],
  "parameters": {},
  "created_by_id": 1
}
```

Run it (from the repository root):

```sh
PYTHONPATH=database:pipeline:service PORT=5002 \
  service/.venv/bin/python -m evolvingclass_pipeline.app
```

Environment: `DATABASE_URL` (default `pipeline/dev.db`), `CONTENT_ROOT`
and `PREVIEW_ROOT` (default `./var/content`, `./var/previews`), `HOST`
(default `127.0.0.1`), `PORT` (default `5002`). Or `docker compose up
generation` for the container on :5002.
