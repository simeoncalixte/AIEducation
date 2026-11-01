# EvolvingClass React frontend

React migration of the Flask pilot UI (SCRUM-173), page by page, with
Storybook interaction tests against the live server (SCRUM-190).

- The Flask app stays live during the migration: each page task ships
  its JSON API plus the React page plus tests, and the Flask route
  retires only after React parity is verified.
- Unmigrated routes render a placeholder linking to the live Flask
  page (the pilot session cookie carries over — same host).

## Reviewer loop (one command)

From `web/frontend`:

```sh
npm run review
```

This seeds fresh demo data into a scratch database, starts the live
API server on `http://127.0.0.1:5001`, and opens Storybook on
`http://127.0.0.1:6006` against it. `PORT` overrides the API port;
`DATABASE_URL` overrides the database (a scratch temp DB by default,
so story resets never touch `web/dev.db`).

The loop: change code, re-run the interaction in Storybook, inspect.
Page stories drive real flows through the UI against the live server
with seeded demo data — no mocked API responses.

## Commands

```sh
npm run dev            # React dev server on :5173 (/api proxied to Flask)
npm run build          # typecheck + production build
npm run storybook      # Storybook on :6006 (needs the API server up)
npm run build-storybook
npm run test-storybook # interaction suite (needs API + Storybook up)
npm run test:live      # fresh temp DB + API + Storybook + suite, one shot
```

`API_URL` overrides the `/api` proxy target for `dev` and `storybook`.
`VITE_API_URL` bakes an absolute API base into the build instead of
the relative `/api` path.

## Layout

- `src/api.ts` — typed `/api/*` client (session cookie auth).
- `src/session.tsx` — session provider (user, login, logout).
- `src/components/` — `Shell` (role-based nav + flash), `ErrorPage`,
  `EmptyState`.
- `src/pages/` — `LoginPage`, `HomePage`, `LogoutPage`,
  `ReviewQueuesPage`, `ReviewDossierPage`, `EditDraftPage`,
  `PlaceholderPage` (unmigrated-route stand-in).
- `src/App.tsx` — client routes for every current Flask page path.
- `src/stories/` — shell stories plus live page stories with play
  functions (`helpers.ts` keeps the shared session order-independent).
- `scripts/review.sh` — reviewer launch; `scripts/test-live.sh` —
  deterministic interaction run for sign-off.
