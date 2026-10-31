# EvolvingClass — Docs Base

This folder is the shared understanding of what is being built. It starts from the
agreed pilot plan and will expand into architecture, data model, asset library,
agent workflow, stage format, analytics, and pilot docs.

## Vision

Teacher-supervised AI agents generate the learning world itself: lesson text and
scripts, AR/VR stages, reusable assets, characters, challenges, and deterministic
goals for students.
Educators brief, review, edit, and approve at asset, stage, and lesson level.
Students play enjoyable, trackable challenges that build correct mental models.
Stages and assets evolve from mastery data and measured educational impact —
reuse and impact are the point, not extras.

## Pilot scope (agreed)

- **Generative core:** agents build lesson text and scripts, stages, assets,
  characters, challenges, and deterministic goals from objectives plus teacher
  briefs. Web pages are briefing/debrief, review surface, and fallback player.
- **Reusable assets:** every asset is versioned, tagged, and parameterized in a
  library; library-first reuse is enforced at review.
- **Educational impact:** per-asset impact scores roll up from student outcomes;
  low-impact assets are flagged for revision or retirement.
- **Deterministic goals:** machine-checkable pass/fail per challenge, replayable
  from stored events; open explanations use teacher-graded rubric goals.
  No LLM grading in pilot.
- **Mental models as the target:** every lesson defines the models students should
  build; challenges construct them and goals verify them, including probing
  common misconceptions.
- **Tracked and enjoyable:** every attempt, goal verdict, and enjoyment signal is
  recorded per student (xAPI-style experience statements + Postgres domain tables).
- **Human gates:** no agent output goes live without a recorded educator approval,
  at asset, stage, and lesson level. Full version history with rollback.
- **Educator direction:** teachers and admins steer agents with recorded directives
  — goal focus and constraints per lesson, class-wide or for particular students —
  and proposals show how they address them.
- **School integration later:** built-in roles for pilot; LTI-based LMS integration
  after the loop works.

## Docs map

- [Plan](plan.md) — goal, success criteria, approach, steps, validation, risks, sources.
- [Architecture](architecture.md) — components, data flows, roles, deployment, phasing.
- [`entities/`](entities/README.md) — one page per table with fields and relationship links.
- [Data model](data-model.md) — Mermaid ERD generated from the live models (39 tables).
- `asset-library.md` — planned: formats, tagging taxonomy, reuse rules, impact scoring.
- `agent-workflow.md` — planned: generator services, proposal formats, gates, prompts policy.
- `stage-format.md` — planned: stage spec — scenes, assets, characters, challenges, goals.
- `analytics.md` — planned: progress, mastery, enjoyment, and asset impact signals.
- `pilot.md` — planned: subject, classrooms, devices, rollout checklist.

## Existing technical base

- Postgres service in `docker-compose.yml`.
- SQLAlchemy 2.0 scaffold in `database/DataModels.py` (`Base`, `TimestampMixin`).
- Python project in `database/pyproject.toml`; migrations via Alembic.
- Schema-guarantee tests in `database/tests/` (stdlib unittest).
