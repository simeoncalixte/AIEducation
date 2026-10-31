# `verdict_override`

Teacher correction of a goal verdict, with the corrected outcome stored.
Append-only history: several rows may exist per verdict; the latest by
(created_at, id) wins. Applied at read time and kept out of evaluator replay
input, so replay stays deterministic. Corrected outcomes feed mastery evidence
and impact rollups.

## Fields

| Field | Type | Notes |
| id | PK | |
| verdict_event | FK → [experience_event](experience_event.md) | The goal-verdict being corrected |
| teacher | FK → [app_user](app_user.md) | |
| reason | text | Required, never silent |
| corrected_passed | boolean | Replacement pass/fail |
| corrected_score | real, nullable | Replacement score, when applicable |
| created_at | timestamp | Ordering for latest-wins |

## Relationships

- Corrects one [experience event](experience_event.md); recorded by a teacher
