# `mental_model`

A target understanding a lesson version must build. Versioned with the
lesson version so rewording a model never rewrites the meaning of historical
mastery. Challenges construct it through doing; goals verify it.

## Fields

| Field | Type | Notes |
| id | PK | |
| lesson_version | FK → [lesson_version](lesson_version.md) | |
| statement | text | The understanding students should walk away with |
| position | int | Order within the lesson version |

Reusable challenges map into each lesson's targets through
[goal_mental_model](goal_mental_model.md) rows: the mapping, not the goal,
carries lesson specificity.

## Relationships

- Belongs to a [lesson version](lesson_version.md)
- Has [misconceptions](misconception.md)
- Verified by [goals](goal.md) via [goal_mental_model](goal_mental_model.md)
- Measured by [mastery records](mastery_record.md)
