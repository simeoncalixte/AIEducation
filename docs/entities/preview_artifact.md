# `preview_artifact`

Server-rendered preview of a draft or published version. Reviewers inspect
draft previews; publish finalizes them, so review diffs and client initial
paint always match the approved version.

## Fields

| Field | Type | Notes |
| id | PK | |
| asset_version | FK → [asset_version](asset_version.md), nullable | Target |
| stage_version | FK → [stage_version](stage_version.md), nullable | Target |
| kind | enum{poster, turntable} | |
| storage_ref | text | Rendered artifact location |
| rendered_at | timestamp | |

Constraint: exactly one target is set. Produced by publish-time background jobs;
pilot uses lightweight stills.

## Relationships

- Depicts one [asset](asset_version.md) or [stage](stage_version.md) version
