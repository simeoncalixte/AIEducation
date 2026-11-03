# `experience_event`

Actor–verb–object telemetry (xAPI-style) plus goal verdicts.

Replay contract: input is client-origin events ordered by `sequence_no`
(unique per attempt); verdicts are recomputed, never replayed as input.
Ingestion is idempotent on (attempt, client_event_id). Late events (sequence
at or below the attempt's evaluated watermark) are stored and flagged by
derivation, but excluded from already-issued verdicts; each verdict payload
records the consumed sequence watermark and evaluator version.

## Fields

| Field | Type | Notes |
| id | PK | |
| attempt | FK → [attempt](attempt.md) | |
| client_event_id | text | Idempotency key, unique per attempt |
| sequence_no | int | Per-attempt ordering, unique per attempt |
| schema_version | text | Event schema version (default v1) |
| origin | enum{client, server} | Client verbs exclude goal-verdict/teacher-evaluation (CHECK) |
| device | FK → [device](device.md), nullable | Reporting device |
| actor | FK → [app_user](app_user.md) | Usually the student; teacher for flags |
| verb | text | attempted, completed, scored, retried, rated, goal-verdict, teacher-evaluation, launch-decision, asset-used, teacher-flagged, … |
| object_type | text | e.g. challenge, goal, asset, stage, lesson |
| object_ref | text | Target identifier |
| goal | FK → [goal](goal.md), nullable | Set for goal-verdicts and teacher-evaluations (repeat teacher grades append; latest wins at read time) |
| challenge_version | FK → [asset_version](asset_version.md), nullable | Kind must be challenge |
| asset_version | FK → [asset_version](asset_version.md), nullable | Set for asset-used |
| stage_version | FK → [stage_version](stage_version.md), nullable | Stage in play |
| asset_use | FK → [asset_use](asset_use.md), nullable | Exact placement instance (disambiguates repeat uses) |
| evaluator_version | text, nullable | Rule engine version behind a verdict |
| payload | json | Telemetry detail |
| occurred_at | timestamp, nullable | Client occurrence time (created_at is server receipt) |
| created_at | timestamp | |

## Relationships

- Belongs to an [attempt](attempt.md); acted by a [user](app_user.md)
- References [goals](goal.md), [asset versions](asset_version.md), [stage versions](stage_version.md), [asset uses](asset_use.md)
- Verdicts may carry [verdict overrides](verdict_override.md); cited by [mastery evidence](mastery_evidence.md)
