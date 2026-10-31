# `goal_mental_model`

Join: which mental models each goal verifies.

## Fields

| Field | Type | Notes |
| goal | FK → [goal](goal.md) | Composite PK with mental_model |
| mental_model | FK → [mental_model](mental_model.md) | Composite PK with goal |

## Relationships

- Links [goals](goal.md) to [mental models](mental_model.md)
