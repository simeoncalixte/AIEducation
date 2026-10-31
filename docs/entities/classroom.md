# `classroom`

A class within a school. Unit of teaching, assignment, and progress views.

## Fields

| Field | Type | Notes |
| id | PK | |
| school | FK → [school](school.md) | |
| name | text | |
| created_at, updated_at | timestamp | |

## Relationships

- Belongs to [school](school.md)
- Has [memberships](membership.md) (students, teachers)
- Has [lessons](lesson.md) (classroom-scoped)
- Receives [assignments](assignment.md); progress aggregates per classroom
