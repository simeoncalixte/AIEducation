# `attempt`

One run of an assignment by a student. Pins versions at session open so a
mid-session publish never disrupts play. Retries open new attempts.

## Fields

| Field | Type | Notes |
| id | PK | |
| assignment | FK → [assignment](assignment.md) | |
| student | FK → [app_user](app_user.md) | |
| pinned_lesson_version | FK → [lesson_version](lesson_version.md) | Resolved at open |
| retry_of | FK → [attempt](attempt.md), nullable | Parent attempt when this is a retry |
| started_at, finished_at | timestamp | finished_at nullable until done |

## Relationships

- Runs an [assignment](assignment.md) for a student
- Pins one [lesson version](lesson_version.md) plus [attempt pins](attempt_pin.md)
- Emits [experience events](experience_event.md)
