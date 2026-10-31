# `consent_record`

Explicit consent history: grant and withdrawal rows accumulate, so
grant–revoke–grant cycles are preserved. Current state is the latest row per
(student, type, policy). Enforcement points (camera/AR use, AI interaction,
analytics) check current state in the service; retention and deletion policy
is still an open pilot decision.

## Fields

| Field | Type | Notes |
| id | PK | Ordering for latest-wins, with created time |
| student | FK → [app_user](app_user.md) | |
| guardian | FK → [app_user](app_user.md), nullable | When guardian consent is required |
| consent_type | text | Category of processing or feature |
| policy_version | text | Policy the consent was given under |
| granted_at | timestamp, nullable | |
| revoked_at | timestamp, nullable | |
| source | text | Where consent was captured |

## Relationships

- Belongs to a student, optionally via a guardian [user](app_user.md)
