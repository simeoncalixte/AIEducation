# EvolvingClass teacher web UI

Server-rendered Flask pages: login with student/teacher/admin roles,
role-based navigation and route guards (SCRUM-122), the review queues
for asset, stage, and lesson proposals (SCRUM-124: diffs, rationale,
directive coverage, reuse matches, impact scores, and the
approve / reject / edit / publish / rollback / retire actions with a
full audit trail) — plus SCRUM-15: the lesson list and brief form,
where a teacher brief becomes a kind=`brief` directive and a lesson
draft proposal — plus SCRUM-28: publish-time preview finalization
with per-version artifacts on asset and stage dossiers —
plus SCRUM-27/29: usage refs, low-impact flags with evidence,
and the asset revise action — plus SCRUM-123/17: the per-lesson
directives panel (class-wide and per-student steering with edit and
deactivate) and scoped briefs — plus SCRUM-125/18: assignment flow
and live per-student progress with inline overrides and flags —
plus SCRUM-19: verdict-override and misconception-flag actions —
plus SCRUM-126/20: the student player (assignment home, briefing,
challenges with progress, debrief, ratings, retry) —
plus SCRUM-21: the admin audit (school status, filterable history).

## Run it

From the repository root:

```sh
PYTHONPATH=database:pipeline:service:web service/.venv/bin/python -m evolvingclass_web.seed  # demo data (once)
PYTHONPATH=database:pipeline:service:web PORT=5001 service/.venv/bin/python -m evolvingclass_web.app
```

Then open http://127.0.0.1:5001 in a browser and log in with a
pilot login name (see the seeded users). Pilot login uses login names
only; passwords arrive with school SSO post-pilot.

`DATABASE_URL` selects the database (default: `web/dev.db`);
`FLASK_SECRET` sets the session key; `PORT` selects the port
(default 5000 — use 5001 on macOS, where AirPlay often holds 5000).
`PREVIEW_DIR` selects the preview render root (unset disables
publish-time preview finalization).

## Test it

```sh
cd web
PYTHONPATH=/Users/simeon/Projects/EvolvingClass/database:/Users/simeon/Projects/EvolvingClass/pipeline:/Users/simeon/Projects/EvolvingClass/service \
  ../service/.venv/bin/python -m unittest discover -s tests -v
```

## React frontend (SCRUM-173) + Storybook (SCRUM-190)

`frontend/` holds the React migration: each page task ships its JSON
API (see `evolvingclass_web/api.py`, served alongside the Flask pages
under `/api/*`) plus the React page plus tests. Flask routes retire
only after React parity is verified; unmigrated React routes link out
to the live Flask page.

Reviewer loop (one command, from `web/frontend`):

```sh
npm run review
```

This seeds demo data, starts the live API server on `:5001`, and
opens Storybook on `:6006` against it. Page stories drive real flows
through the UI with seeded demo data — no mocked API responses. For a
deterministic sign-off run (fresh temp database):

```sh
npm run test:live
```

See `frontend/README.md` for all commands and the review loop.

## Layout

- `evolvingclass_web/app.py` — Flask factory, routes, action handlers.
  Handlers are thin: decisions and edits go through
  `evolvingclass_service.review`, publishing through
  `evolvingclass_service.publication`.
- `evolvingclass_web/present.py` — view-model builders (queues, diffs,
  directive coverage, reuse matches, impact rows, audit, lesson list,
  brief context). Returns plain
  dicts; templates never see ORM instances.
- `evolvingclass_web/seed.py` — demo data via the real service calls.
- `evolvingclass_web/templates/` — Jinja pages: login, home, error,
  queues, dossier, edit form, lesson list, brief form, directives,
  assignments, briefing, challenge, debrief, audit.
