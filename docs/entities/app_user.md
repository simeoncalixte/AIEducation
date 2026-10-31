# `app_user`

Built-in pilot account. School SSO and LMS launch arrive post-pilot via LTI.

## Fields

| Field | Type | Notes |
| id | PK | |
| role | enum{student, teacher, admin, guardian} | |
| display_name | text | |
| login_ref | text | Pilot credential handle (unique) |
| created_at, updated_at | timestamp | |

## Relationships

- Has [memberships](membership.md) (one user, several memberships allowed)
- Authors [directives](directive.md), [approvals](approval.md), [comments](comment.md)
- Gives [ratings](rating.md) (educators; student enjoyment flows as events)
- Targeted by per-student [directives](directive.md) and [assignments](assignment.md)
- Owns [attempts](attempt.md) (as student); records [verdict overrides](verdict_override.md) (as teacher)
- Linked as guardian via [student_guardian](student_guardian.md); named in [consent records](consent_record.md)
