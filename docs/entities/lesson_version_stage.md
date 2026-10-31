# `lesson_version_stage`

Pins stage versions into a lesson version, in order. This is what makes a
published lesson reproducible: rollback restores this exact composition, and
attempt pins derive from it. Personal variants get their own rows.

## Fields

| Field | Type | Notes |
| id | PK | |
| lesson_version | FK → [lesson_version](lesson_version.md) | |
| stage_version | FK → [stage_version](stage_version.md) | Pinned version |
| position | int | Order within this lesson version (unique per version) |
| required | boolean | |

Unique on (lesson_version, position) and (lesson_version, stage_version).

## Relationships

- Composes [lesson versions](lesson_version.md) from pinned [stage versions](stage_version.md)
