# `asset_tag`

One taxonomy tag on an asset version: subject, objective, age band, role, style.

## Fields

| Field | Type | Notes |
| id | PK | |
| asset_version | FK → [asset_version](asset_version.md) | |
| taxonomy | enum{subject, objective, age_band, role, style} | |
| value | text | Controlled vocabulary per taxonomy |

Objectives are controlled tag values in pilot — no separate objectives table.

## Relationships

- Belongs to [asset_version](asset_version.md)
