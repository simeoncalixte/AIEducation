# `scene_requirement`

A capability a stage version needs (required) or prefers. Answers: can this
student's device run this stage, and which fallback applies if not?

## Fields

| Field | Type | Notes |
| id | PK | |
| stage_version | FK → [stage_version](stage_version.md) | |
| capability | text | Shared vocabulary with device capabilities |
| required | boolean | Required = must have; preferred = degrade gracefully |

## Relationships

- Belongs to a [stage version](stage_version.md); checked against [device capabilities](device_capability.md) at assignment and launch
