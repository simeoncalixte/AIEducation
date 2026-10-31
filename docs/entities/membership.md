# `membership`

Links a user into the roster. Students and teachers join classrooms; admins
join schools. Revocation ends access without deleting history.

## Fields

| Field | Type | Notes |
| id | PK | |
| user | FK → [app_user](app_user.md) | |
| classroom | FK → [classroom](classroom.md), nullable | Set for students/teachers |
| school | FK → [school](school.md), nullable | Set for admins |
| status | enum{active, revoked} | |
| joined_at | timestamp | |
| left_at | timestamp, nullable | Set on revocation/withdrawal |

Constraints: exactly one of classroom/school is set, matching the user's role;
unique per (user, classroom) and per (user, school).

## Relationships

- Belongs to [app_user](app_user.md), [classroom](classroom.md), [school](school.md)
