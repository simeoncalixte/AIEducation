# `publish_event`

Audit log for publish, rollback, and retire actions on exactly one version.
Publishing itself is a service transaction (validate approvals and
dependencies, freeze the content graph, flip status); this table is the
durable record that it happened.

## Fields

| Field | Type | Notes |
| id | PK | |
| asset_version | FK → [asset_version](asset_version.md), nullable | Target |
| stage_version | FK → [stage_version](stage_version.md), nullable | Target |
| lesson_version | FK → [lesson_version](lesson_version.md), nullable | Target |
| action | enum{published, rolled_back, retired} | |
| actor | FK → [app_user](app_user.md) | |
| rationale | text | |
| created_at | timestamp | |

Constraint: exactly one target is set.

## Relationships

- Audits one version; recorded by a [user](app_user.md)
