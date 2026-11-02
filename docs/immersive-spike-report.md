# Immersive slice spike report (SCRUM-7 / SCRUM-25)

Plan step 3: retire device risk first with a static fixture stage on real
pilot hardware. Targets from `docs/plan.md`: poster first paint under 2s
on pilot devices; telemetry-to-verdict p95 under 5s.

Status: server-side proof complete; **pilot-device measurements and the
pool list are TBD — see "Needs pilot run" below.**

## Method

- Fixture: React `/xr-fixture` route rendering `XRFixtureStage`
  (poster-first three.js volcano diorama, paint-timing overlay vs the
  2s target, capability panel, Enter-AR session button). Stories:
  `XR/Fixture` (`FixtureLoads`, `OrbitDrag`).
- Telemetry: generic idempotent intake
  (`POST /api/play/attempt/<id>/events`) plus the existing
  answer→evaluate path; latency probe over the real HTTP app
  (test client, 100 answers + 50 debrief reads).
- Fallback/resume: web player on the persisted attempt, checkpoint
  save/latest endpoints, resume-after-close API test.

## Measured (server-side, observed this session)

| Check | Result | Target | Verdict |
|---|---|---|---|
| Answer record+evaluate p50 / p95 / max | 5.77 / 7.25 / 9.80 ms | p95 < 5000 ms | PASS |
| Debrief verdict-read p50 / p95 / max | 1.39 / 1.81 / 2.87 ms | p95 < 5000 ms | PASS |
| Intake idempotency | replay returns `duplicate:true`, row count stable | exact | PASS |
| Fallback resume | fresh client resumes same open attempt, answers intact | exact | PASS |
| Checkpoint sequences | monotonic per attempt, pinned-stage enforced | exact | PASS |

Suites: `test_api_events` 9/9, `test_api_checkpoints` 9/9,
checkpoints+play+events 26/26, pipeline 46/46; `tsc`, `vite build`,
`storybook build` clean. Full web suite 193/194 with the single
failure being the known pre-existing `test_date_filters` timezone
flake (5/5 under `TZ=UTC`).

## Storybook viewability map

| Spike behavior | Story |
|---|---|
| Fixture load, timings, caps, AR button, orbit | `XR/Fixture` |
| Telemetry answer → verdicts rendered | `Pages/Debrief` `AnsweredRoundTrip` |
| Briefing start → Continue resume | `Pages/Briefing` `PublishedBriefing` |
| Empty debrief, rate, finish, retry | `Pages/Debrief` |
| Challenge guards (index, attempt, auth) | `Pages/Challenge` |

## Needs pilot run (TBD)

On each pool device, open `/xr-fixture` (see repo test steps) and record:

| Device (model + browser) | Poster ms / PASS | First-frame ms | immersive-ar | AR session starts | Notes |
|---|---|---|---|---|---|
| TBD | | | | | |
| TBD | | | | | |

Also still open: device-network telemetry-to-verdict E2E (server
budget measured above leaves ~5s of headroom for the network leg).

## Follow-ups recorded, not built

- Generic-event-triggered evaluation → SCRUM-10 event intake story.
- XR-client event emission from the fixture → SCRUM-10 AR delivery.
- Model-backed stage/lesson authoring → SCRUM-30 to SCRUM-34.
