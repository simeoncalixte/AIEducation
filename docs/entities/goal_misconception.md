# `goal_misconception`

Join: which misconceptions each goal probes.

## Fields

| Field | Type | Notes |
| goal | FK → [goal](goal.md) | Composite PK with misconception |
| misconception | FK → [misconception](misconception.md) | Composite PK with goal |

## Relationships

- Links [goals](goal.md) to [misconceptions](misconception.md)
