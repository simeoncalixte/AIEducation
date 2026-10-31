# `lesson`

A teachable unit: ordered stages pursuing objectives and mental models.

## Fields

| Field | Type | Notes |
| id | PK | |
| school | FK → [school](school.md) | |
| classroom | FK → [classroom](classroom.md), nullable | Null = school-level lesson |
| subject | text | Pilot: one subject |
| title | text | |
| created_at, updated_at | timestamp | |

## Relationships

- Has [lesson versions](lesson_version.md) (which define [mental models](mental_model.md)) and [stages](stage.md)
- Targeted by [directives](directive.md); given out via [assignments](assignment.md)
