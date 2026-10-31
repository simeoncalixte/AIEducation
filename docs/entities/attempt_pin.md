# `attempt_pin`

Pins one stage version into an attempt at session open.

## Fields

| Field | Type | Notes |
| id | PK | |
| attempt | FK → [attempt](attempt.md) | |
| stage_version | FK → [stage_version](stage_version.md) | Current published version at open |

## Relationships

- Links [attempts](attempt.md) to pinned [stage versions](stage_version.md)
