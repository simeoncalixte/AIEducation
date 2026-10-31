# `comment`

Review discussion on a version.

## Fields

| Field | Type | Notes |
| id | PK | |
| asset_version | FK → [asset_version](asset_version.md), nullable | Target |
| stage_version | FK → [stage_version](stage_version.md), nullable | Target |
| lesson_version | FK → [lesson_version](lesson_version.md), nullable | Target |
| author | FK → [app_user](app_user.md) | |
| body | text | |
| created_at | timestamp | |

Constraint: exactly one target is set.

## Relationships

- Discusses one version; authored by a [user](app_user.md)
