# `mastery_record`

Stored mastery estimate per student per mental model. The evolution loop reads
these rows to find model gaps worth new proposals.

## Fields

| Field | Type | Notes |
| id | PK | |
| student | FK → [app_user](app_user.md) | |
| mental_model | FK → [mental_model](mental_model.md) | |
| objective | text, nullable | Objective tag value, when finer than the model |
| score | real | Current estimate |
| confidence | real | |
| updated_at | timestamp | |

## Relationships

- Belongs to a student and a [mental_model](mental_model.md)
- Explained by [mastery evidence](mastery_evidence.md)
