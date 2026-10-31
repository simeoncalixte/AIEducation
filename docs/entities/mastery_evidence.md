# `mastery_evidence`

Explains a mastery score: weighted links to the verdicts and events behind it.

## Fields

| Field | Type | Notes |
| id | PK | |
| mastery_record | FK → [mastery_record](mastery_record.md) | |
| experience_event | FK → [experience_event](experience_event.md), nullable | Verdict or signal |
| source | text | e.g. goal-verdict, teacher-evaluation, teacher-flag |
| weight | real | |
| observed_at | timestamp | |

## Relationships

- Supports one [mastery record](mastery_record.md); cites [experience events](experience_event.md)
