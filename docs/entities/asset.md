# `asset`

Reusable library item identity. Versioning, reuse, and impact all hang off
versions. Characters and challenges are asset kinds — no separate tables.

## Fields

| Field | Type | Notes |
| id | PK | |
| kind | enum{environment, prop, media, text, script, character, challenge} | Fixed at creation |
| title | text | |
| created_by | FK → [app_user](app_user.md) | Agent service or educator account |
| school | FK → [school](school.md), nullable | Owning school (null = platform) |
| visibility | enum{school, shared} | Who may reuse it |
| created_at, updated_at | timestamp | |

## Relationships

- Has [asset versions](asset_version.md)
