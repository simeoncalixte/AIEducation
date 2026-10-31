# `goal`

One check on a challenge version. Deterministic goals evaluate from telemetry
via the rules engine (same events always yield the same verdict); teacher-graded
goals carry a rubric and are judged by a teacher from recorded evidence. Goals
verify the lesson's target mental models — not mere completion — and probe
anticipated misconceptions. No LLM grading in pilot.

## Fields

| Field | Type | Notes |
| id | PK | |
| challenge_version | FK → [asset_version](asset_version.md) | Kind must be challenge |
| key | text | Stable within the challenge |
| rule | json | Thresholds, counts, sequences, spatial conditions (deterministic goals) |
| evaluation | enum{deterministic, teacher} | |
| rubric | json, nullable | Criteria for teacher-graded goals |
| template_ref | text | Per-challenge-type template it was drafted from |
| created_at, updated_at | timestamp | |

## Relationships

- Belongs to a challenge [asset version](asset_version.md)
- Verifies [mental models](mental_model.md) via [goal_mental_model](goal_mental_model.md); probes [misconceptions](misconception.md) via [goal_misconception](goal_misconception.md)
- Produces [experience events](experience_event.md) (goal-verdict, teacher-evaluation)
