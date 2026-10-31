# `impact_rollup`

Computed effectiveness of one asset version over a window. Observational
signals, not proof: several assets act together, and retries can mean
confusion as easily as enjoyment. Revision flags require minimum evidence
thresholds (sample size first) defined alongside the formula.

## Fields

| Field | Type | Notes |
| id | PK | |
| asset_version | FK → [asset_version](asset_version.md) | |
| window | text | e.g. 7d, 30d, all |
| mastery | real | Gain signal from goal verdicts (corrected outcomes applied) |
| completion | real | Completion signal |
| enjoyment | real | Ratings, retry, replay signals |
| sample_size | int | Events/students behind the scores |
| formula_version | text | Scoring formula version |
| cohort | text, nullable | e.g. classroom set or pilot group |
| uncertainty | real, nullable | Spread/confidence where computed |
| baseline | json, nullable | Comparison baseline snapshot |
| computed_at | timestamp | |

## Relationships

- Scores one [asset version](asset_version.md). Asset-level scores aggregate
  published versions; low scores flag revision or retirement in review.
