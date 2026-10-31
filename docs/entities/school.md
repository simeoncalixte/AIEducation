# `school`

Top-level tenant. Pilot runs one school; the schema supports many.

## Fields

| Field | Type | Notes |
| id | PK | |
| name | text | |
| created_at, updated_at | timestamp | |

## Relationships

- Has many [classrooms](classroom.md)
- Has many [memberships](membership.md) (admins)
- Scopes [lessons](lesson.md)
