# `device`

A student device, for capability matching and event attribution.

## Fields

| Field | Type | Notes |
| id | PK | |
| student | FK → [app_user](app_user.md) | |
| label | text | e.g. classroom tablet 12 |
| created_at | timestamp | |

## Relationships

- Belongs to a student; reports [device capabilities](device_capability.md)
- Attributed on [experience events](experience_event.md)
