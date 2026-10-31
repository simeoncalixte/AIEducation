# `stage_version`

Immutable composed spec: ordered [asset uses](asset_use.md) (scene, characters,
challenges, text).

## Fields

| Field | Type | Notes |
| id | PK | |
| stage | FK → [stage](stage.md) | |
| version_no | int | Monotonic per stage |
| status | enum{draft, published, retired} | |
| rationale | text | |
| generation_run | FK → [generation_run](generation_run.md), nullable | Null = human-authored |
| directive_snapshot | json, nullable | Exact directives the proposal acted on |
| created_at, updated_at | timestamp | |

## Relationships

- Belongs to [stage](stage.md); composes [asset uses](asset_use.md)
- Gated by [approvals](approval.md); discussed via [comments](comment.md), [ratings](rating.md)
- Composed into lessons via [lesson_version_stage](lesson_version_stage.md); audited via [publish events](publish_event.md)
- Depicted by [preview artifacts](preview_artifact.md); pinned by [attempt pins](attempt_pin.md); emits [experience events](experience_event.md)
