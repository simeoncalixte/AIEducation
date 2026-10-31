# `asset_use`

Pins one asset version into a lesson, stage, or challenge spec.

## Fields

| Field | Type | Notes |
| id | PK | |
| asset_version | FK → [asset_version](asset_version.md) | Pinned version |
| lesson_version | FK → [lesson_version](lesson_version.md), nullable | Target |
| stage_version | FK → [stage_version](stage_version.md), nullable | Target |
| challenge_version | FK → [asset_version](asset_version.md), nullable | Target; kind must be challenge |
| position | int | Order within the target spec |
| role | text | e.g. scene, guide, task, narration |
| param_overrides | json | Per-use parameter values |

Constraint: exactly one target is set.

## Relationships

- Links [asset versions](asset_version.md) into lesson, stage, and challenge specs
