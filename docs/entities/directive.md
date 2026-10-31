# `directive`

Recorded educator steering. Briefs are directives of kind brief — one table
covers initial direction and later steering. Stage proposals inherit their
lesson's directives.

## Fields

| Field | Type | Notes |
| id | PK | |
| lesson | FK → [lesson](lesson.md) | |
| student | FK → [app_user](app_user.md), nullable | Null = class-wide; set = particular student |
| kind | enum{brief, steer} | |
| focus | text | Goal focus |
| constraints | json | Must-include / must-avoid |
| priority | int | |
| author | FK → [app_user](app_user.md) | Teacher or admin |
| active | boolean | |
| created_at, updated_at | timestamp | |

## Relationships

- Targets [lesson](lesson.md), optionally one student
- Authored by a teacher/admin [user](app_user.md)
- Snapshotted into proposal versions (`directive_snapshot`); addressed by proposal rationales
