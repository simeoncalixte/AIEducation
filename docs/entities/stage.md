# `stage`

Ordered scene within a lesson. One or more stages per lesson.

## Fields

| Field | Type | Notes |
| id | PK | |
| lesson | FK → [lesson](lesson.md) | |
| position | int | Canonical order; per-version order lives in [lesson_version_stage](lesson_version_stage.md) |
| title | text | |
| created_at, updated_at | timestamp | |

## Relationships

- Belongs to [lesson](lesson.md); has [stage versions](stage_version.md)
