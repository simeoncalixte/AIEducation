# EvolvingClass service layer

Transactional application services over `database/DataModels.py`.
This package owns the **publication workflow** promised by
`docs/architecture.md`:

- `publish_*` validates approvals and dependency closure, flips
  `draft -> published`, and writes the `publish_event` audit row in one
  database transaction.
- `rollback_*` restores a retired version to live (`retired -> published`)
  while demoting the currently live version (`published -> retired`),
  with one audit row per flip.
- `retire_*` takes a live version out of service (`published -> retired`).
- `resolve_current_lesson_version` picks the live version a student
  should be served (personal variant wins over the class default).
- `submit_brief` (SCRUM-15) persists a kind=`brief` directive and drafts
  a lesson proposal with rationale, objectives, mental models, and a
  directive snapshot in one transaction.
- `publish_asset_version` / `publish_stage_version` accept an optional
  `finalize_preview` renderer (SCRUM-28); its artifact is pinned to
  the version in the same transaction unless one already exists.
- `revise_asset_version` (SCRUM-29) drafts a new version from a
  published or retired one, carrying content, tags, and goals over
  with lineage in its rationale; existing pins are untouched.
- `create_steer_directive` / `update_directive` /
  `deactivate_directive` (SCRUM-123, SCRUM-17) manage class-wide and
  per-student steering; per-student targets must belong to the lesson
  classroom. `submit_brief` accepts an optional student scope for
  personal variants.
- `assign_lesson` (SCRUM-125, SCRUM-18) assigns a lesson to exactly
  one classroom or student, idempotently.
- `record_verdict_override` / `flag_misconception` (SCRUM-19) append
  corrections with a required reason and record teacher-observed
  misconceptions as server events.
- `evaluate_attempt` (SCRUM-20) issues deterministic goal verdicts
  from client telemetry; same events always yield the same verdicts.
- `start_attempt` / `answer_challenge` / `finish_attempt` /
  `rate_lesson` / `retry_attempt` (SCRUM-126, SCRUM-20) run student
  play against pinned versions.
- `ensure_draft` is the freeze guard: mutating writers must call it
  before touching a version graph, so published/retired content is
  immutable by service rule (the DB enforces identity and FK shape).

Authorization rule (pilot): only teachers and admins with an **active**
membership in the owning classroom or school may publish, roll back, or
retire. Global assets (`school_id IS NULL`) additionally require the
admin role.

Run the tests with the service venv:

```sh
cd service
PYTHONPATH=/Users/simeon/Projects/EvolvingClass/database \
  .venv/bin/python -m unittest discover -s tests -v
```

Against live Postgres (`e2test` database in the compose container):

```sh
cd service
EVOLVECLASS_TEST_DATABASE_URL="postgresql+psycopg://evolvingclass:evolvingclass@localhost:5432/e2test" \
PYTHONPATH=/Users/simeon/Projects/EvolvingClass/database \
  .venv/bin/python -m unittest discover -s tests -v
```
