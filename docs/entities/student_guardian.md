# `student_guardian`

Guardian link for a minor. Placeholder depth for pilot; consent flows build on it.

## Fields

| Field | Type | Notes |
| id | PK | |
| student | FK → [app_user](app_user.md) | |
| guardian | FK → [app_user](app_user.md) | Role must be guardian |
| relationship | text | e.g. parent, caretaker |
| is_primary | boolean | |
| status | enum{active, revoked} | |
| created_at | timestamp | |

## Relationships

- Links a student to a guardian [user](app_user.md); cited by [consent records](consent_record.md)
