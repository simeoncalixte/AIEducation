# `approval`

One gate decision on exactly one version. Rejections stay readable for audit.
Approvals feed the publication transaction, which validates them plus all
dependencies before flipping status and writing a [publish event](publish_event.md).

## Fields

| Field | Type | Notes |
| id | PK | |
| asset_version | FK → [asset_version](asset_version.md), nullable | Target |
| stage_version | FK → [stage_version](stage_version.md), nullable | Target |
| lesson_version | FK → [lesson_version](lesson_version.md), nullable | Target |
| actor | FK → [app_user](app_user.md) | Teacher or admin |
| decision | enum{approved, rejected} | |
| rationale | text | |
| decided_at | timestamp | |

Constraint: exactly one target is set.

## Relationships

- Gates one [asset](asset_version.md), [stage](stage_version.md), or [lesson](lesson_version.md) version
- Cast by an educator [user](app_user.md)
