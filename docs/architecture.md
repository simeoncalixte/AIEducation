# EvolvingClass — Architecture

Status: draft. Companion to [Plan](plan.md). This doc explains the application
end to end: the full walkthrough from brief to evolution, the components, their
responsibilities, and how data flows between them for the Web + AR/VR pilot.

## Context and constraints

- **Generative core:** agents build lesson text and scripts, AR/VR stages, assets,
  characters, challenges, and deterministic goals. The generated lesson and world
  are the product; web pages are briefing/debrief, review surface, and fallback
  player.
- **Reuse and impact are requirements:** every asset must be reusable across
  stages, and every asset's educational impact must be measurable from student
  outcome data. Content without reuse and impact tracking is out of scope.
- **Deterministic goals:** challenge verdicts come from a rules engine over event
  telemetry, replayable from stored events. Open explanations use teacher-graded
  rubric goals. No LLM grading in pilot.
- **Mental models are the target:** each lesson defines the models students should
  build; challenges construct them through doing and goals verify them, including
  probing anticipated misconceptions.
- **Supervised at three levels:** assets, stages, and lessons each follow
  draft → review → publish with recorded approvals. Educators direct agents with
  recorded directives per lesson — class-wide or for particular students.
- **Assigned, not browsed:** students play what is assigned to their classroom or
  to them individually; per-student directives personalize the generated result.
- **Existing base:** Postgres via `docker-compose.yml`, SQLAlchemy 2.0 scaffold
  in `database/DataModels.py` (`Base`, `TimestampMixin`), migrations via Alembic
  (`database/` project). New domain tables extend this scaffold.

## End-to-end walkthrough

One lesson's full life, pilot scope:

1. **Brief and direct.** A teacher (or school admin) sets objectives, target
   mental models, and directives: goal focus plus must-include/must-avoid
   constraints, class-wide or for particular students.
2. **Generate.** The generation plane queries the Asset Library, builds only what
   is missing, and authors text, scripts, characters, challenges, and
   deterministic goals into a stage spec — emitted as proposals with draft
   previews, never live state.
3. **Review and publish.** The teacher reviews asset, stage, and lesson levels
   (diffs, rationale, reuse and impact data), edits, and approves. The
   publication transaction validates approvals and dependencies, publishes
   immutable versions, finalizes previews, and writes publish events.
4. **Assign.** The published lesson is assigned to a classroom or to individual
   students; per-student directives resolve to the right variant at serve time.
5. **Play.** The student opens the assignment on web or immersive, starting from
   the server-rendered poster while 3D loads. The runtime pins the published
   version in use, so a mid-session publish never disrupts play, and streams
   telemetry as experience events.
6. **Verdicts and progress.** The goals evaluator turns telemetry into
   deterministic goal verdicts. Progress, verdicts, and enjoyment signals update
   teacher views in the same session.
7. **Feedback.** Teachers flag misconceptions, adjust directives, and rate or
   comment on assets; students rate and retry. All feedback is recorded.
8. **Evolution.** Mastery and mental-model gaps plus per-asset impact scores raise
   new proposals (stage variants, asset revisions) into the review queue.
   Teachers accept, edit, or reject; accepted proposals publish as new versions,
   and the loop continues.

## Component overview

```text
+----------------+   +-------------------+   +------------------+
| Review / Admin |   | Generation plane  |   | Asset Library    |
| UI: asset,     |<->| (agent services): |<->| versioned,       |
| stage, lesson  |   | assets, stages,   |   | tagged, impact-  |
| review, audit  |   | text, scripts,    |   | scored           |
| directives     |   | characters,       |   |                  |
+-------+--------+   | challenges, goals |   +--------+---------+
        |            +---------+---------+            |
        +------------+---------v---------+            |
                     |  Python service   |<-----------+
                     |  API + approvals  |
                     |  + assignments +  |
                     |  goals evaluator  |
                     +---+-----------+---+
                +--------+           +--------+
                | Web player|        | AR/VR view|
                | briefing/ |        | (WebXR    |
                | fallback  |        | runtime)  |
                +-----------+        +-----------+
                             |
                    +--------v---------+
                    |  Postgres:       |
                    |  rosters, assets,|
                    |  stages, goals,  |
                    |  versions,       |
                    |  approvals,      |
                    |  directives,     |
                    |  assignments,    |
                    |  events, impact  |
                    +------------------+
```

### 1. Asset Library

The heart of reuse. Stores versioned assets (scene props, environments, media,
lesson text, scripts, character definitions, challenge templates) with:

- Tags: subject, objective, age band, role, style constraints.
- Parameters: the knobs that let one asset serve many stages (sizes, counts,
  palettes, difficulty variables).
- Usage references: which lesson, stage, and challenge versions use each version.
- Impact scores: rolled up from student outcome data (mastery gain, completion,
  enjoyment) for challenges using the asset.
- Previews: server-rendered poster frames and turntable clips per version,
  produced at publish time. Review queues and clients use them for instant
  initial views without loading interactive 3D.

Library-first rule: generation briefs and reviewers prefer existing assets over
new one-offs. Editing an asset creates a new version; existing stages keep
working until re-approved against it.

### 2. Generation plane (agent services)

Bounded agent services with typed inputs and versioned proposal outputs. Runs
move queued → running → completed/failed/cancelled, with attempt counts and
last errors for retry triage; proposals snapshot the active directives:

- **Asset generator:** builds new assets from briefs when the library has no
  suitable match; emits asset + tags + objective mapping + rationale.
- **Stage assembler:** composes scenes from library assets plus new builds;
  emits a stage spec + rationale.
- **Character authoring:** defines characters (role, dialogue bounds, scene
  behaviors) as reviewable assets, not free-form chatbots.
- **Challenge authoring:** defines interactive tasks with their telemetry
  contract (which events the runtime must emit).
- **Lesson text and script authoring:** briefings, explanations, debriefs,
  dialogue, narration, and character/scene behavior scripts — versioned and
  reviewable like any other asset.
- **Goal authoring:** drafts deterministic goals per challenge from
  per-challenge-type templates (thresholds, counts, sequences, spatial
  conditions). Goals verify the lesson's target mental models — not mere
  completion — and probe anticipated misconceptions. Teacher-graded goals carry
  a rubric instead of a rule.

Every output is a proposal: a draft version plus rationale and objective mapping —
no separate proposal table. Nothing in this plane writes live state; all
proposals go through approvals.

### 3. Python service (API + approvals + assignments + goals evaluator)

One deployable service in pilot:

- **Identity:** built-in pilot accounts (student, teacher, school admin);
  school SSO and LMS launch arrive post-pilot via LTI.
- **Roster and authz:** schools, teachers, classrooms, students,
  classroom-scoped roles.
- **Assignments:** lessons assigned to classrooms or individual students;
  per-student variants and directives resolved at serve time.
- **Versioned stores:** assets, stages, lessons with immutable versions,
  publish state, rollback.
- **Three-level approval gates:** asset, stage, and lesson publishes each
  require an approval record (who, what version, when). Rejections stay readable
  for audit.
- **Goals evaluator:** rules engine that turns challenge telemetry into goal
  verdicts. Deterministic and replayable: re-running stored events yields the
  same verdicts. Teacher overrides are recorded with reasons, never silent.
- **Event intake:** experience events from both runtimes, keyed to attempt with
  idempotency key, per-attempt sequence (unique), schema version, and
  client/server origin. Instance identity comes from the asset-use ref;
  stage attribution from the stage-version ref. Ingestion is idempotent on
  (attempt, client_event_id); gaps are tolerated, duplicates rejected.
  Client-origin rows may never carry goal-verdict or teacher-evaluation verbs
  (CHECK plus service rejection). Replay input is client-origin events in
  sequence order under the recorded evaluator version; verdicts are recomputed,
  never replayed. Late events (at or below the attempt's evaluated watermark,
  recorded in each verdict payload) are stored but excluded from issued
  verdicts.
- **Preview renderer:** server-side background jobs that render poster frames and
  turntable previews for each proposed and published asset/stage version.
  Reviewers inspect draft previews; publish finalizes them. Artifacts are
  versioned with the content they depict, so review diffs and client initial
  paint always match the approved version. Pilot uses lightweight stills to
  avoid a GPU dependency; full pixel-streamed 3D is explicitly out of pilot.

### 4. Web player

Lesson briefing/debrief pages (server-rendered for fast first paint and
shareable links), review-adjacent previews, assigned-lesson player, and the
fallback player when immersive is unavailable. Stage views open on the
server-rendered poster frame while interactive 3D loads. Emits the same
experience events as the immersive runtime so progress is renderer-independent.

### 5. AR/VR view (immersive runtime)

Runs approved assigned stages through WebXR: scene rendering, character
behaviors, challenge interactions, and telemetry emission per the challenge's
event contract. Capability detection up front (checked against scene
requirements) with automatic web fallback; the fallback reuses the same pinned
versions through the web renderer, so no alternate stage is needed in pilot.
Progress is preserved across the switch, and checkpoint state carries renderer
plus schema version for future web/immersive conversion. Loading screens show
the stage's server-rendered poster.

### 6. Review / admin UI

- Per-level queues (asset, stage, lesson) with diffs, agent rationale, objective
  mapping, and — for existing assets — reuse and impact data.
- Directives panel: teachers and admins set goal focus and constraints per lesson
  — class-wide or for particular students. Stage proposals inherit their lesson's
  directives, and must show how they address the active ones.
- Assignment view: assign published lessons to classrooms or students, and see
  per-student progress, verdicts, and enjoyment signals.
- Comment/edit/approve/reject actions; rollback to any prior version through a
  normal approval record.
- School admin view: cross-classroom status, approvals audit, progress and
  enjoyment summaries.

### 7. Postgres (system of record)

Single store in pilot: the tables in Domain entities below. Served directly for
classroom views in pilot; a dedicated analytics pipeline is post-pilot
(see `analytics.md`, planned).

## Domain entities (ERD input)

Canonical table list for `data-model.md`. Detail pages with fields and links:
[entities/](entities/README.md). Decisions embedded here are binding unless the
ERD turn revisits them explicitly.

**People and rosters.** `school`, `classroom` (school FK), `app_user` (role:
student, teacher, admin), `membership`: students and teachers link to
classrooms, admins link to schools. One user can hold several memberships.

**Lessons and stages.** `lesson` (classroom/school scope, subject), immutable
`lesson_version` (status draft/published/retired, rationale, objective refs,
optional per-student scope: null = class default, set = personal variant).
`stage` belongs to a lesson (ordered, one or more per lesson); immutable
`stage_version` pins the composed spec. `lesson_version_stage` pins ordered
stage versions into each lesson version, so rollback restores exact
composition; attempt pins derive from it. Assignments reference lessons; the
runtime resolves and pins the current published version at session open.

**Assets (uniform).** `asset` + immutable `asset_version` with kind enum
{environment, prop, media, text, script, character, challenge}. Characters and
challenges are asset kinds — no separate tables — so versioning, approvals,
reuse, and impact scoring work uniformly. Challenge versions carry the telemetry
contract; `goal` rows (challenge version FK, key, rule, template ref) carry the
deterministic checks. `asset_tag` values (subject, objective, age band, role,
style); objectives are controlled tag values in pilot, no separate table.
`asset_use` links asset versions into lesson, stage, and challenge specs, pinned
by version, ordered, with role and parameter overrides.

**Mental models.** `mental_model` (lesson version FK, statement),
`misconception` (mental model FK, description, probe notes). Goals reference
the models they verify (`goal_mental_model`) and the misconceptions they probe
(`goal_misconception`). Reusable challenges map into each lesson's targets
through these joins: the mapping, not the goal, carries lesson specificity.

**Direction and gates.** `directive` (lesson FK, student FK nullable: null =
class-wide; kind brief/steer; focus, constraints, priority, author, active
flag). Briefs are directives of kind brief — one table covers initial direction
and later steering. `approval` references exactly one asset, stage, or lesson
version (actor, decision, rationale, timestamp); rejections stay readable. A
proposal is a draft version plus rationale — no separate proposal table.
`comment` and `rating` target versioned records for review discussion and
enjoyment/quality signals. `publish_event` audits each publish, rollback, and
retire action per version.

**Assignment and play.** `assignment` (lesson FK plus exactly one of classroom
FK / student FK). `attempt` (student, assignment, pinned lesson/stage versions,
retry parent, started/finished); retries open new attempts linked to the prior
one. `experience_event` (attempt FK, idempotency key, per-attempt sequence,
schema version, client/server origin, actor–verb–object, refs to
goal/challenge/asset/stage/instance, evaluator version, payload, occurrence and
receipt timestamps). Goal verdicts are events; `verdict_override` (verdict event
FK, teacher, reason, corrected outcome, timestamp) is append-only history with
latest-wins, applied at read time and kept out of evaluator replay input.

**Derived and rendered.** `impact_rollup` per asset version (window, mastery /
completion / enjoyment scores, sample size, formula version, cohort,
uncertainty, baseline); asset-level scores aggregate published versions.
Rollups are observational signals with minimum evidence thresholds, not proof.
`preview_artifact` per draft or published asset/stage version (kind
poster/turntable, storage ref). Library misses are noted on the resulting
proposal, not a separate table.

**Runtime and devices.** `device` (student, label), `device_capability`
(reported capability keys), `scene_requirement` (stage version, capability,
required/preferred): matched at assignment and launch to pick the stage or its
fallback. `session_checkpoint` (attempt, stage version, sequence, state) for
resume after close or drop.

**Mastery.** `mastery_record` (student, mental model, score, confidence) with
`mastery_evidence` (weighted links to verdicts and events). The evolution loop
reads these rows to find model gaps worth new proposals.

**Provenance.** `generation_run` (agent/model/prompt refs, params, status
queued/running/completed/failed/cancelled, attempts, last error, policy
version); asset, stage, and lesson versions carry a nullable run ref (null =
human-authored) plus a snapshot of the directives the run acted on. Full
input/output lineage is deferred.

**Consent.** `student_guardian` (student, guardian user, relationship, primary,
status) and `consent_record` (student, guardian, type, policy version,
append-only grant/revoke history with latest-wins, source). Enforcement points
check current state in the service; retention and deletion stay open pilot
decisions.

## Asset lifecycle

```text
brief → generate → review → publish → reuse → score → revise / retire
```

- New assets are only generated on a library miss, with the miss noted on the
  resulting proposal.
- Impact scoring runs off challenge outcomes; low-impact assets surface in the
  review queue for revision or retirement.
- Retirement never deletes history: past stages keep their pinned versions.

## Publication, freeze, and rollback

Publishing is a service transaction, not a status flip:

1. Validate: required approvals exist; every referenced version (composition,
   asset uses, goals) is published; the content graph has no dangling drafts.
2. Flip status draft → published and write a `publish_event` row, atomically.
3. Freeze: rows linked to a published version (goals, asset uses, scene
   requirements, composition entries) become immutable — enforced by service
   write guards, since the database cannot express "frozen through a join".

What lives where: the database enforces identity, FK integrity, CHECKs,
uniques, and the audit trail; the service enforces approval presence,
dependency closure, freeze, and version-resolution rules. Rollback publishes a
prior version (new publish event, status flips on both versions); history is
never unpublished or rewritten. Current version at serve time: latest
published version matching the student (personal scope first, else class
default), ties by highest version_no.

## Key data flows

**Generation:** teacher brief + directives (goal focus, constraints per lesson —
class-wide or per-student) → stage assembler queries library →
asset generator fills misses → text, script, character, challenge, and goal
authoring complete the stage spec → teacher reviews asset, stage, and lesson
levels → publish.

**Assignment and play:** published lesson assigned to classroom or students →
student opens the assignment on web or immersive → runtime pins the published
version and loads it → telemetry streams to the service as experience events →
goals evaluator issues verdicts → progress, verdicts, and enjoyment signals
update teacher views in the same session. Retries start new attempts against the
same pinned version. Sessions checkpoint for resume after close or drop.

**Evolution and impact:** threshold rules over stored events (evaluated at each
session close and nightly) raise gap proposals — stage variants, asset
revisions — into the review queue. Teachers accept, edit, or reject; accepted
proposals publish as new versions. Nothing auto-publishes. Teachers see which
signals triggered each proposal and each asset's track record before approving.

## Roles and permissions (pilot)

| Actor        | Scope     | Can do                                                        |
| ------------ | --------- | ------------------------------------------------------------- |
| Student      | Classroom | Play assigned stages, rate, retry                             |
| Teacher      | Classroom | Brief, direct agents, review/approve, publish, rollback       |
| School admin | School    | Direct agents, review all levels, audit approvals, view school|

Cross-school access is out of pilot scope. All approval, publish, override, and
retirement actions record actor, timestamp, and version.

**Authorization invariants (service-enforced before endpoints land):**
lesson.classroom must belong to lesson.school; attempt pins must belong to the
assignment's lesson; reused assets must satisfy visibility scope (school-owned
vs shared); per-student directives and assignments must target students of the
lesson classroom; revoked memberships authorize nothing. The database cannot
express these cross-row rules, so each gets a named service check with a test.

## Deployment (pilot)

- Postgres from the existing `docker-compose.yml`, plus the Python service next
  to it. Schema changes ship as Alembic migrations from `database/`.
- Web player, immersive view, and review UI are clients of the one service API;
  no direct database access from clients.
- Seed content for one pilot subject ships as versioned fixtures (library assets
  + stages + goals), not hand edits.
- Preview renders run as background jobs next to the service, with artifacts
  stored alongside their content versions. Pilot uses lightweight stills.

## Phasing (maps to plan steps)

1. Domain + asset/stage/goal schema → 2. web authoring/review/player →
   3. immersive slice spike → 4. asset pipeline + library → 5. stage
   generation → 6. immersive delivery + goal evaluation → 7. evolution +
   impact loop → 8. pilot hardening. Steps 4 and 6 can overlap once
   steps 1–3 land.

## Relation to the v2 ERD spec

`ar_stem_platform_erd_specification_v2.md` (repo root) is a production-wide
reference, not the pilot baseline. This doc's decisions are binding for pilot.
Adopted from v2: version pinning, memberships, composition via a join table,
publish audit, idempotent event ingestion, checkpoints, mastery record plus
evidence, minimal generation provenance, device/requirement matching, consent
placeholders, teacher-graded rubric path. Deferred post-pilot: full RBAC,
courses/terms/offerings, standards graph, agent sessions/messages,
simulations/anchors, assessments/questions, validation framework,
safety/moderation, audit beyond the publish log, retention/deletion,
accessibility, localization, publication-audience, sharing/forks, generic
artifact layer. Superseded by pilot requirements: mental models as first-class
targets, teacher→agent directives, challenges as asset kinds, per-asset impact
scoring, attempts per assignment run, objectives as tags.

## Open decisions (for expansion docs)

- Asset formats, tagging taxonomy, and reuse rules → `asset-library.md` (planned).
- Server-rendered preview formats, turntable clips, and render budget →
  `asset-library.md` (planned).
- Stage spec schema (scenes, assets, text/scripts, characters, challenges, goals,
  mental models) → `stage-format.md` (planned).
- Goal template set per challenge type → `stage-format.md` (planned).
- Assignment model and per-student variant resolution → `data-model.md` (planned).
- Impact-score formula and revision/retirement thresholds → `analytics.md` (planned).
- Agent proposal formats (including text/script conventions) and rationale
  requirements → `agent-workflow.md` (planned).
- Content-validation rules and generated-script sandbox policy →
  `agent-workflow.md` (planned).
- Retention, deletion/anonymization, and guardian access surface →
  `pilot.md` (planned).
- LMS integration surface → post-pilot via LTI; pilot keeps built-in roles.
