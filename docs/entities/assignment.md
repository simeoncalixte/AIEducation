# `assignment`

Gives a lesson to a classroom or to one student. References the lesson —
versions resolve at serve time: latest published version matching the student
(personal scope first, else class default); ties break by highest version_no.

## Fields

| Field | Type | Notes |
| id | PK | |
| lesson | FK → [lesson](lesson.md) | |
| classroom | FK → [classroom](classroom.md), nullable | Target |
| student | FK → [app_user](app_user.md), nullable | Target |
| assigned_by | FK → [app_user](app_user.md) | Teacher or admin |
| due_at | timestamp, nullable | |
| created_at, updated_at | timestamp | |

Constraint: exactly one of classroom/student is set.

## Relationships

- Gives a [lesson](lesson.md) to a [classroom](classroom.md) or student
- Attempted via [attempts](attempt.md)
