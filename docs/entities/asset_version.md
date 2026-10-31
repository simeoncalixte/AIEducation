# `asset_version`

Immutable version of a library asset. Challenge versions carry the telemetry
contract; text/script versions carry lesson copy and behavior scripts.

## Fields

| Field | Type | Notes |
| id | PK | |
| asset | FK → [asset](asset.md) | |
| version_no | int | Monotonic per asset |
| status | enum{draft, published, retired} | |
| rationale | text | Includes library-miss note when generated on a miss |
| objective_refs | text[] | Controlled tag values |
| content_ref | text | Spec/body location |
| param_schema | json | Reusable knobs (sizes, counts, palettes, difficulty) |
| generation_run | FK → [generation_run](generation_run.md), nullable | Null = human-authored |
| directive_snapshot | json, nullable | Exact directives the proposal acted on |
| created_at, updated_at | timestamp | |

## Relationships

- Belongs to [asset](asset.md); tagged by [asset tags](asset_tag.md)
- Used via [asset uses](asset_use.md) (pinned wherever referenced)
- Checked by [goals](goal.md) (kind = challenge)
- Gated by [approvals](approval.md); discussed via [comments](comment.md), [ratings](rating.md); audited via [publish events](publish_event.md)
- Scored by [impact rollups](impact_rollup.md); depicted by [preview artifacts](preview_artifact.md)
- Referenced by [experience events](experience_event.md) (asset-used)
