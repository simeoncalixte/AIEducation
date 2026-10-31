## Goal

Build EvolvingClass as a teacher-supervised platform where AI agents generate the
learning world itself: lesson text and scripts, AR/VR stages, reusable assets,
characters, challenges, and deterministic goals for students. Web + AR/VR pilot:
agents build lessons and immersive stages from learning objectives and teacher
direction; educators review, edit, and approve
at asset, stage, and lesson level; students play trackable, enjoyable challenges;
stages and assets evolve from mastery data and measured educational impact.

## Success Criteria

- Agents generate complete lessons and stages: lesson text and scripts, scene
  composition, assets, characters, challenges, and deterministic goals from
  objectives plus a teacher brief.
- Every generated asset enters a versioned, tagged, reusable library; reuse across
  stages is measurable and part of review.
- Every challenge ships deterministic goals: machine-checkable pass/fail criteria
  that give the same verdict for the same performance, replayable from stored events;
  open explanations use teacher-graded rubric goals.
- Every lesson defines its target mental models; challenges and goals are designed
  to build and verify them, including probing anticipated misconceptions.
- Teachers and admins can direct agents toward particular goals for a particular
  lesson — either class-wide or for particular students; directives are recorded
  and proposals show how each one is addressed.
- Every attempt, goal verdict, and enjoyment signal is recorded per student and
  visible by classroom.
- Teachers/admins can comment, edit, approve, reject, and roll back assets, stages,
  and lessons.
- Asset educational impact is scored from student outcome data; low-impact assets
  are flagged for revision or retirement.
- Pilot runs on the existing Postgres-backed Python service with versioned schema
  migrations.
- Pilot targets (initial — ratify with the pilot teacher before hardening):
  ≥70% of pilot students pass deterministic goals by their 3rd attempt;
  teacher review under 15 minutes per stage; poster first paint under 2s on
  pilot devices; telemetry-to-verdict p95 under 5s; generation cost tracked
  per stage draft with a cap set after the spike.

## Approach

**Generative core: stages, assets, characters, challenges.** The product is not
lesson text with 3D attached. Agents build the lesson and the stage: lesson text and scripts (dialogue,
narration, scene and character behaviors), scene composition, 3D and media assets,
characters (guides, actors, opponents), interactive challenges, and the
deterministic goals that judge them. Web pages serve as briefing/debrief, review
surface, and fallback player.

**Reusable asset library with educational-impact scoring.** Every asset is
versioned, tagged (subject, objective, age band, role), and parameterized for
reuse. Reuse is a review criterion: reviewers prefer library assets over one-off
generation. Impact is measured: challenge events using an asset roll up into
per-asset effectiveness (mastery gain, completion, enjoyment); low-impact assets
are flagged for revision or retirement. Without this loop the project is just
content sprawl.

**Lesson text, scripts, characters, and challenges.** Agents generate lesson text
(briefings, explanations, debriefs) and scripts (dialogue, narration, character
and scene behaviors) as versioned, reviewable assets. Characters are directed
agents with roles, dialogue bounds, and scene behaviors, reviewed like any other
asset. Challenges are interactive tasks (build, find, assemble, decide) that emit
in-scene telemetry for goal evaluation.

**Deterministic goals, no LLM grading in pilot.** Each challenge defines
machine-checkable goals (thresholds, counts, sequences, spatial conditions)
evaluated from event telemetry by a rules engine. Same performance always yields
the same verdict. Open-ended explanations that rules cannot judge use
teacher-graded rubric goals, evaluated by a teacher from recorded evidence.
Replay consumes client-origin events in sequence order; verdicts are
recomputed, never replayed. Teachers can read every goal and override a verdict
with a recorded reason.

**Mental models as the learning target.** Each lesson names the mental models
students should walk away with. Challenges are built to construct those models
through doing, and goals verify the model — not just task completion. Known
misconceptions are anticipated per lesson and explicitly probed, so a student who
completes steps with the wrong understanding still fails the goal. Evolution
targets detected model gaps with new variants.

**Supervised gates at three levels.** Assets, stages, and lessons each follow
draft → review → publish with recorded approvals. Agents propose; educators
dispose. Educators also steer: teachers and admins issue directives targeting a
lesson — either class-wide or for particular students — carrying goal focus,
must-include/must-avoid constraints, and priority. Stage proposals inherit their
lesson's directives, and every proposal shows how it addresses the active ones.
Publish is a transaction validated against approvals and dependencies, recorded
as a publish event; rows linked to published versions are frozen. Full version
history and rollback at each level.

**Track with experience statements plus domain tables.** Record learning as
actor–verb–object style experience statements into a Learning Record Store (LRS)
pattern, backed by Postgres domain tables for rosters, lessons, and progress
(verdicts plus event aggregates — no separate grades table in pilot). This
follows the xAPI model: an IEEE standard describing a "JSON data
model format and a RESTful Web Service API for communication between Activities …
and a Learning Record Store (LRS)" for "tracking and accessing experiential data,
especially in learning" ([standard](https://standards.ieee.org/ieee/9274.1.1/7321/)),
summarized as collecting "a wide range of experiences a person has (online and
offline)" in a consistent format ([overview](https://xapi.com/overview/)). Goal
verdicts, asset usage, and enjoyment signals (completion, retry, choice, ratings)
are first-class events, not afterthoughts.

**Immersive via the web API, not native apps (pilot).** Use WebXR as the single
web API for reaching AR now and VR later: the spec "describes support for
accessing virtual reality (VR) and augmented reality (AR) devices, including
sensors and head-mounted displays, on the Web"
([spec](https://immersive-web.github.io/webxr/)). Rejected for pilot: separate
native AR and VR apps, which would triple runtime work before the generation loop
is proven.

**School integration later, not a pilot blocker.** Defer LMS launch/rostering to
Learning Tools Interoperability (LTI), which "allows learning management systems
(LMS) or platforms to integrate remote tools and content in a standard way"
([standard](https://www.1edtech.org/standards/lti)). Pilot uses built-in
school/teacher/classroom/student roles; LTI is the integration phase after the
loop works.

**Assumptions:** one pilot subject and classroom set; a small pool of AR-capable
phones or headsets is available for the AR/VR track; web is the fallback when
immersive is unavailable.

## Steps

1. **Domain, roles, and asset/stage/goal schema.** Add the tables in
   architecture's Domain entities (schools, memberships, lesson/stage/asset
   versions, composition, mental models, directives, approvals, publish log,
   assignments, attempts, events, overrides, rollups, previews, mastery,
   provenance, devices, checkpoints, consent) to `database/DataModels.py`;
   generate Alembic migration. Depends on: nothing.
2. **Web authoring, review, and fallback player.** Teacher briefs and directives
   (goal focus and constraints per lesson, class-wide or per-student), review
   queues with diffs,
   lesson briefing/debrief pages, student web player emitting progress events.
   Depends on: step 1.
3. **Immersive slice spike.** Static fixture stage on a real pilot device:
   capability check, telemetry round-trip, web fallback, checkpoint resume.
   Exit criteria: poster first paint, verdict latency, and fallback behavior
   measured; device pool confirmed. Depends on: steps 1–2.
4. **Asset generation pipeline and library.** Agents build assets into the
   versioned library with objective mapping; library-first reuse rule enforced at
   review; proposal and publish trigger server-rendered previews. Depends on:
   steps 1–2.
5. **Stage generation.** Scene assembly from library plus new assets, lesson text,
   script, character, and challenge authoring, mental-model definition plus
   deterministic goal authoring per challenge — all behind approval gates.
   Depends on: steps 1–2, 4.
6. **AR/VR delivery with telemetry and goal evaluation.** WebXR stage runtime,
   capability detection with web fallback, event telemetry feeding the rules
   engine for goal verdicts. Depends on: steps 1–3, 5.
7. **Evolution and educational-impact loop.** Mastery plus impact signals propose
   new stage variants and asset revisions; per-asset impact scores flag
   low-impact assets for revision or retirement; teachers approve everything.
   Depends on: steps 4–6.
8. **Pilot hardening.** Admin audit views, classroom progress and enjoyment views,
   seed content for one subject. Depends on: steps 2–7.

## Validation Plan

- `uv run alembic upgrade head` from `database/` creates all tables cleanly on a
  fresh database.
- Focused service tests via the standard library runner cover versioning,
  three-level approval gates (no live write without approval at any level), and
  goal-evaluator replay (same stored events always produce the same verdict).
- End-to-end pilot script: teacher brief → generated stage → teacher
  review/edit/approve → assign to classroom → student plays on web and AR →
  progress, goal verdicts, and enjoyment signals visible in the classroom view.
- Reuse check: one library asset used in two stages; editing it creates new
  versions requiring re-approval without breaking existing stages.
- Impact demo: seeded outcome data produces per-asset impact scores and flags a
  low-impact asset for revision.
- Mental-model check: seeded misconception telemetry fails the goal despite task
  completion, and triggers a targeted variant proposal for teacher review.
- Direction check: a recorded directive (e.g. new goal focus for a lesson, or a
  per-student adjustment) appears in the next proposal's rationale and diff.
- Early device smoke (step 3): static fixture stage on a real pilot device —
  capability check, telemetry round-trip, web fallback, checkpoint resume.
  **Highest-risk check, run first: this immersive session plus telemetry
  capture on actual pilot hardware.**
- Full AR smoke on a real pilot device: launch an approved generated stage,
  complete one challenge, confirm telemetry and goal verdict land in the
  student record; verify web fallback when immersive is unavailable.

## Risks / Open Questions

- **Generation quality and cost:** unreviewed generated 3D is worse than none;
  mitigation is mandatory gates plus the library-first reuse rule and a small
  seed asset set.
- **Goal-authoring burden:** every challenge needs checkable goals; mitigation is
  agent-drafted goals from per-challenge-type templates, teacher-reviewed.
- **Visual and pedagogical consistency:** mitigation is style/palette and
  objective constraints in generation briefs, enforced at review.
- **Device fragmentation:** AR/VR behavior varies across hardware; mitigation is
  capability detection plus guaranteed web fallback and a small approved-device
  pool for pilot.
- **Student data handling:** classroom-scoped roles and audit events from day one;
  district policy review before wider rollout.
- **Open:** which subject and classroom pilots first (default: one subject, one
  teacher, 1–2 classrooms)? Which exact device pool is available (default:
  whatever the pilot school already owns, phones first)?

## Sources

- https://immersive-web.github.io/webxr/
- https://standards.ieee.org/ieee/9274.1.1/7321/
- https://xapi.com/overview/
- https://www.1edtech.org/standards/lti
