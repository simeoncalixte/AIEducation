# Entities

One page per table, with fields and relationship links. Source of truth for
what exists; [architecture](../architecture.md) stays the source of truth for
why. The visual diagram is the [ERD](../data-model.md), generated from the
live SQLAlchemy metadata.

Convention: several tables target "exactly one version" — one of
[asset_version](asset_version.md), [stage_version](stage_version.md), or
[lesson_version](lesson_version.md). The physical form (nullable FKs vs.
polymorphic columns) is an ERD decision.

## People and rosters

- [school](school.md) — tenant; has classrooms, admin memberships, lessons
- [classroom](classroom.md) — class; unit of assignment and progress views
- [app_user](app_user.md) — built-in pilot account: student, teacher, admin
- [membership](membership.md) — user → classroom (student/teacher) or school (admin)

## Lessons and stages

- [lesson](lesson.md) — teachable unit with ordered stages
- [lesson_version](lesson_version.md) — immutable; drafts are proposals; optional per-student scope
- [stage](stage.md) — ordered scene within a lesson
- [stage_version](stage_version.md) — immutable composed spec
- [lesson_version_stage](lesson_version_stage.md) — pins stage versions per lesson version
- [publish_event](publish_event.md) — publish/rollback/retire audit per version

## Assets

- [asset](asset.md) — library identity; characters and challenges are kinds, not tables
- [asset_version](asset_version.md) — immutable; telemetry contract on challenges
- [asset_tag](asset_tag.md) — subject, objective, age band, role, style
- [asset_use](asset_use.md) — pins asset versions into lesson/stage/challenge specs
- [goal](goal.md) — deterministic check on a challenge version
- [goal_mental_model](goal_mental_model.md) — which models each goal verifies

## Mental models

- [mental_model](mental_model.md) — target understanding per lesson version
- [misconception](misconception.md) — anticipated wrong understanding, explicitly probed
- [goal_misconception](goal_misconception.md) — which goals probe which misconceptions

## Direction and gates

- [directive](directive.md) — recorded steering; briefs are kind brief
- [approval](approval.md) — gate decision on exactly one version
- [comment](comment.md) — review discussion on a version
- [rating](rating.md) — educator quality signal on a version

## Assignment and play

- [assignment](assignment.md) — lesson to a classroom or one student
- [attempt](attempt.md) — one run; pins versions; retries open new attempts
- [attempt_pin](attempt_pin.md) — stage version pinned into an attempt
- [experience_event](experience_event.md) — actor–verb–object telemetry plus verdicts
- [verdict_override](verdict_override.md) — teacher correction, applied at read time

## Derived and rendered

- [impact_rollup](impact_rollup.md) — effectiveness per asset version and window
- [preview_artifact](preview_artifact.md) — server-rendered poster/turntable per published version

## Runtime and devices

- [device](device.md) — student device for capability matching and attribution
- [device_capability](device_capability.md) — one reported capability per device
- [scene_requirement](scene_requirement.md) — capability a stage version needs or prefers
- [session_checkpoint](session_checkpoint.md) — resume state per attempt

## Mastery

- [mastery_record](mastery_record.md) — stored estimate per student per mental model
- [mastery_evidence](mastery_evidence.md) — weighted links behind a mastery score

## Provenance

- [generation_run](generation_run.md) — minimal AI provenance per version (nullable)

## Consent

- [student_guardian](student_guardian.md) — guardian link for a minor
- [consent_record](consent_record.md) — explicit grant and withdrawal

## Relationship map

```text
school ─┬─ classroom ─┬─ membership ── app_user
        │             ├─ lesson ─┬─ lesson_version ─┬─ asset_use ── asset_version ── asset
        │             │          │                  │                                 ├─ asset_tag
        │             │          │                  │                                 ├─ goal ─┬─ goal_mental_model ── mental_model ── misconception
        │             │          │                  │                                 │        └─ experience_event ── verdict_override
        │             │          │                  ├─ approval / comment / rating    ├─ impact_rollup
        │             │          │                  └─ preview_artifact               └─ preview_artifact
        │             │          ├─ stage ── stage_version ─┬─ asset_use (above)
        │             │          │                          ├─ approval / comment / rating
        │             │          │                          ├─ preview_artifact
        │             │          │                          └─ attempt_pin ── attempt ─┬─ assignment ── lesson
        │             │          ├─ mental_model ── lesson_version (versioned)          ├─ experience_event (above)
        │             │          └─ directive ── app_user (author, student scope)     └─ pinned lesson_version
        │             └─ assignment (above)
        └─ membership (admins)
```

Merged additions:

```text
attempt ── session_checkpoint (resume state)
attempt ── experience_event (idempotent: client_event_id + sequence_no)
student ── mastery_record ── mastery_evidence ── experience_event
student ── device ── device_capability ⟷ scene_requirement ── stage_version
student ── student_guardian ── guardian (user); student ── consent_record
asset / stage / lesson version ── generation_run (nullable; null = human-authored)
goal ── teacher rubric path ── teacher-evaluation events
lesson_version ── lesson_version_stage ── stage_version (reproducible composition)
any version ── publish_event (publish/rollback/retire audit)
goal ── goal_misconception ── misconception (structured probes)
```
