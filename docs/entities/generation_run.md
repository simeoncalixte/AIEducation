# `generation_run`

Minimal AI provenance: one generation invocation behind a version. Versions
carry a nullable run ref (null = human-authored) plus a snapshot of the
directives the run acted on. Full input/output lineage is deferred; rationale
stays on the version.

## Fields

| Field | Type | Notes |
| id | PK | |
| agent_ref | text | Agent name + version |
| model_ref | text | Provider / model / version |
| prompt_ref | text | Template + version |
| params | json | Generation parameters |
| status | enum{queued, running, completed, failed, cancelled} | Retry ownership: failed runs record attempts + last_error for the worker |
| attempts | int | Execution attempts so far |
| last_error | text, nullable | Most recent failure, for retry triage |
| policy_version | text, nullable | Safety/validation policy applied |
| started_at, finished_at | timestamp | finished_at nullable |

## Relationships

- Referenced by [asset](asset_version.md), [stage](stage_version.md), and [lesson](lesson_version.md) versions
