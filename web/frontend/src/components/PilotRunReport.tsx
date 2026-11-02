import {
  LATENCY_BUDGETS,
  PILOT_RUNS,
  POSTER_TARGET_MS,
} from "../xr/pilotRuns";

/** Recorded pilot-run evidence for the immersive spike (SCRUM-25). */
export function PilotRunReport() {
  return (
    <main>
      <h1>Immersive spike — pilot runs</h1>
      <p>
        Recorded device measurements and latency budgets. Numbers mirror{" "}
        <code>docs/immersive-spike-report.md</code>.
      </p>
      <h2>Device runs (poster target ≤{POSTER_TARGET_MS}ms)</h2>
      <table>
        <thead>
          <tr>
            <th scope="col">Device</th>
            <th scope="col">Poster</th>
            <th scope="col">First frame</th>
            <th scope="col">Caps</th>
            <th scope="col">AR session</th>
          </tr>
        </thead>
        <tbody>
          {PILOT_RUNS.map((run) => (
            <tr key={`${run.device}-${run.date}`}>
              <td>
                {run.device}
                <br />
                {run.browser} · {run.date}
              </td>
              <td>
                {run.posterMs}ms {run.posterPass ? "PASS" : "FAIL"}
              </td>
              <td>{run.firstFrameMs}ms</td>
              <td>
                webgl2 {String(run.webgl2)}, webxr {String(run.webxr)},
                immersive-ar {String(run.immersiveAr)}, session{" "}
                {run.session}, ratio {run.pixelRatio}, touch{" "}
                {run.touchPoints}
              </td>
              <td>{run.arResult}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2>Latency budgets (server-side probe)</h2>
      <table>
        <thead>
          <tr>
            <th scope="col">Check</th>
            <th scope="col">p50</th>
            <th scope="col">p95</th>
            <th scope="col">max</th>
            <th scope="col">Verdict</th>
          </tr>
        </thead>
        <tbody>
          {LATENCY_BUDGETS.map((row) => (
            <tr key={row.check}>
              <td>{row.check}</td>
              <td>{row.p50Ms}ms</td>
              <td>{row.p95Ms}ms</td>
              <td>{row.maxMs}ms</td>
              <td>
                target p95 &lt;{row.targetP95Ms}ms{" "}
                {row.p95Ms < row.targetP95Ms ? "PASS" : "FAIL"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
