# EvolvingClass JSON API + React UI

The Flask app serves the JSON `/api/*` only: session auth with
student/teacher/admin roles (SCRUM-122/174/175/176), review queues
and dossiers with approve / reject / edit / publish / rollback /
retire (SCRUM-124), briefs and directives (SCRUM-15/123/17),
assignments and per-student progress (SCRUM-125/18), overrides and
flags (SCRUM-19), the student player endpoints — briefing,
challenges, debrief, ratings, retry (SCRUM-126/20) — audit
(SCRUM-21), checkpoints, event intake, launch routing (SCRUM-10),
and rubric grading (SCRUM-38/129). React (`frontend/`) owns every
page; no HTML is served from Flask.

## Run it

From the repository root:

```sh
PYTHONPATH=database:pipeline:service:web service/.venv/bin/python -m evolvingclass_web.seed  # demo data (once)
PYTHONPATH=database:pipeline:service:web PORT=5001 service/.venv/bin/python -m evolvingclass_web.app
```

The API listens on http://127.0.0.1:5001 (JSON only — use the
React reviewer loop below for pages). Pilot login uses login names
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

`frontend/` holds every page, backed by the JSON API in
`evolvingclass_web/api.py`. All stories render React components
against the live server — no mocked API responses.

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

- `evolvingclass_web/app.py` — Flask factory: session auth guard
  plus the `/api/*` routes (no HTML).
- `evolvingclass_web/api.py` — JSON handlers. Handlers are thin:
  decisions and edits go through `evolvingclass_service.review`,
  publishing through `evolvingclass_service.publication`.
- `evolvingclass_web/present.py` — view-model builders (queues, diffs,
  directive coverage, reuse matches, impact rows, audit, lesson list,
  brief context). Returns plain dicts; callers never see ORM
  instances.
- `evolvingclass_web/seed.py` — demo data via the real service calls.
