# `lesson_version`

Immutable version of a lesson. A proposal is a draft version plus rationale —
no separate proposal table.

## Fields

| Field | Type | Notes |
| id | PK | |
| lesson | FK → [lesson](lesson.md) | |
| version_no | int | Monotonic per lesson |
| status | enum{draft, published, retired} | |
| rationale | text | Agent or educator reasoning |
| objective_refs | text[] | Controlled tag values |
| student_scope | FK → [app_user](app_user.md), nullable | Null = class default; set = personal variant |
| published_at | timestamp, nullable | |
| generation_run | FK → [generation_run](generation_run.md), nullable | Null = human-authored |
| directive_snapshot | json, nullable | Exact directives the proposal acted on |
| created_at, updated_at | timestamp | |

## Relationships

- Belongs to [lesson](lesson.md); optionally scoped to one student
- Composes [asset uses](asset_use.md) (lesson-level text/media)
- Gated by [approvals](approval.md); discussed via [comments](comment.md), [ratings](rating.md)
- Composed via [lesson_version_stage](lesson_version_stage.md); audited via [publish events](publish_event.md)
- Defines [mental models](mental_model.md)
- Resolved and pinned by [attempts](attempt.md) at session open
