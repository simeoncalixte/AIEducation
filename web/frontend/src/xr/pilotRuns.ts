/** Recorded immersive-spike pilot runs (SCRUM-25).
 *
 * Source of truth for the numbers is docs/immersive-spike-report.md;
 * this module mirrors them so the evidence is viewable in Storybook.
 */

export interface PilotDeviceRun {
  device: string;
  browser: string;
  date: string;
  posterMs: number;
  posterPass: boolean;
  firstFrameMs: number;
  webgl2: boolean;
  webxr: boolean;
  immersiveAr: boolean;
  session: string;
  pixelRatio: number;
  touchPoints: number;
  arResult: string;
}

/** Paint target from docs/plan.md. */
export const POSTER_TARGET_MS = 2000;

export const PILOT_RUNS: PilotDeviceRun[] = [
  {
    device: "Pixel 10 Pro",
    browser: "mobile browser via Storybook",
    date: "2026-11-02",
    posterMs: 58,
    posterPass: true,
    firstFrameMs: 138,
    webgl2: true,
    webxr: false,
    immersiveAr: false,
    session: "inline",
    pixelRatio: 2.6,
    touchPoints: 5,
    arResult:
      "pending — Storybook iframe strips xr-spatial-tracking; " +
      "retest on the direct /xr-fixture page",
  },
];

export interface LatencyBudget {
  check: string;
  p50Ms: number;
  p95Ms: number;
  maxMs: number;
  targetP95Ms: number;
}

export const LATENCY_BUDGETS: LatencyBudget[] = [
  { check: "answer record+evaluate", p50Ms: 5.77, p95Ms: 7.25, maxMs: 9.8, targetP95Ms: 5000 },
  { check: "debrief verdict-read", p50Ms: 1.39, p95Ms: 1.81, maxMs: 2.87, targetP95Ms: 5000 },
];
