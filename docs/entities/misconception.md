# `misconception`

An anticipated wrong understanding, explicitly probed so that completing steps
with the wrong model still fails the goal.

## Fields

| Field | Type | Notes |
| id | PK | |
| mental_model | FK → [mental_model](mental_model.md) | |
| description | text | The wrong understanding |
| probe_notes | text | How challenges should surface it |

## Relationships

- Belongs to [mental_model](mental_model.md)
- Probed by [goals](goal.md) via [goal_misconception](goal_misconception.md)
