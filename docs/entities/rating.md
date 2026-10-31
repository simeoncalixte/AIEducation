# `rating`

Enjoyment/quality signal on a version, from educators. Student enjoyment flows
as [experience events](experience_event.md) (rated verb), not rows here.

## Fields

| Field | Type | Notes |
| id | PK | |
| asset_version | FK → [asset_version](asset_version.md), nullable | Target |
| stage_version | FK → [stage_version](stage_version.md), nullable | Target |
| lesson_version | FK → [lesson_version](lesson_version.md), nullable | Target |
| author | FK → [app_user](app_user.md) | Teacher or admin |
| score | int | 1–5 (CHECK-enforced) |
| created_at | timestamp | |

Constraint: exactly one target is set.

## Relationships

- Scores one version; given by an educator [user](app_user.md)
