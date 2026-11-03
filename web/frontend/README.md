# EvolvingClass React frontend

React UI for the EvolvingClass pilot (SCRUM-173), with Storybook
interaction tests against the live server (SCRUM-190). React owns
every page; the Flask app serves the JSON `/api/*` only.

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
npm run dev            # React dev server on :5173 (/api proxied to the API server)
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
- `src/pages/` — one page per route (`LoginPage`, `HomePage`,
  `ReviewQueuesPage`, `ChallengePage`, `GradingPage`, …).
- `src/App.tsx` — client routes for every page path.
- `src/stories/` — shell stories plus live page stories with play
  functions (`helpers.ts` keeps the shared session order-independent).
- `scripts/review.sh` — reviewer launch; `scripts/test-live.sh` —
  deterministic interaction run for sign-off.
