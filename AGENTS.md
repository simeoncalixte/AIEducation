# AGENTS.md

## Code Map

- `database` - application source
- `pipeline` - application source
- `docs` - project documentation

## Conventions

- Place database tests in the tests directory under the database directory.
- Write Python modules with the .py extension.

## Jira

- Treat the Jira ticket (summary, description, acceptance criteria, subtasks) as the contract before starting SCRUM work; fetch it via the Jira REST API with `JIRA_URL`, `JIRA_EMAIL`, and the `JIRA` API token from `.env` (never print or commit the token).
- Update ticket status while working: move to In Progress when starting, to In Review when the work is ready for agent review, and back to To Do if the work is paused or blocked. Only the user moves tickets to Done.
- Review tickets in the review lane (In Review): move the ticket to AI Review, verify every acceptance criterion against the build (run the relevant test suites), then move it to Human Review. If the review finds gaps, fix them (moving back to In Progress while reworking) and re-review; only review-clean tickets reach Human Review.
- Always add a comment when moving a ticket to Human Review, describing what was verified and why it is ready for human review. Never comment on Jira issues otherwise unless the user explicitly asks.
