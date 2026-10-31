# `session_checkpoint`

Resume state for an attempt: restores scene and progress after the client
closes or the connection drops.

## Fields

| Field | Type | Notes |
| id | PK | |
| attempt | FK → [attempt](attempt.md) | |
| stage_version | FK → [stage_version](stage_version.md) | Pinned version in use |
| checkpoint_sequence | int | Monotonic per attempt |
| state | json | Scene + progress snapshot; carries renderer + schema_version for future web/immersive conversion |
| created_at | timestamp | |

## Relationships

- Belongs to [attempt](attempt.md); references a pinned [stage version](stage_version.md)
