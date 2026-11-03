import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  api,
  type Challenge,
  type DebriefVerdict,
} from "../api";
import {
  createFixtureStage,
  probeXR,
  type FixtureHandle,
  type XRSupport,
} from "../xr/fixtureScene";
import {
  STAGE_LOADED_VERB,
  buildCheckpointState,
  collectCapabilities,
  createTelemetryQueue,
  gateImmersive,
  parseCheckpointView,
  readStashedCheckpoint,
  stashCheckpoint,
  type GuideIdentity,
  type TelemetryQueue,
} from "../xr/runtimeClient";

/** Poster first-paint target from docs/plan.md. */
const POSTER_TARGET_MS = 2000;

const POSTER_SRC =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 600'%3E%3Cdefs%3E%3ClinearGradient id='s' x1='0' y1='0' x2='0' y2='1'%3E%3Cstop offset='0' stop-color='%237fb2e5'/%3E%3Cstop offset='.62' stop-color='%23dcebf5'/%3E%3Cstop offset='.63' stop-color='%234a4640'/%3E%3Cstop offset='1' stop-color='%23282624'/%3E%3C/linearGradient%3E%3CradialGradient id='g' cx='.5' cy='.35' r='.25'%3E%3Cstop offset='0' stop-color='%23ffb066'/%3E%3Cstop offset='1' stop-color='%23ff5a1f' stop-opacity='0'/%3E%3C/radialGradient%3E%3C/defs%3E%3Crect width='800' height='600' fill='url(%23s)'/%3E%3Cpolygon points='180,380 400,150 620,380' fill='%233a3f44'/%3E%3Cpolygon points='340,205 400,150 460,205 430,215 370,215' fill='%23282624'/%3E%3Cellipse cx='400' cy='208' rx='34' ry='10' fill='url(%23g)'/%3E%3Cellipse cx='400' cy='208' rx='16' ry='5' fill='%23ff7a2a'/%3E%3C/svg%3E";

type SessionState =
  | { kind: "checking" }
  | { kind: "unavailable"; reason: string }
  | { kind: "ready" }
  | { kind: "starting" }
  | { kind: "presenting" }
  | { kind: "failed"; reason: string };

export interface XRFixtureStageProps {
  /** Attempt link enables launch gating, telemetry, checkpoints. */
  attemptId?: number;
  stageVersionId?: number;
  /** 1-based challenge served in scene (SCRUM-35/128). */
  challengeIndex?: number;
  /** Guides from the challenge view; same identity as web (SCRUM-200). */
  guides?: GuideIdentity[];
}

/**
 * Fixture volcano stage: poster first, then the live three.js diorama
 * with paint timings, capability report, and an Enter-AR session
 * button. Timings measure from component mount (a direct page load
 * lands here, so mount is close to navigation start).
 *
 * Linked to an attempt (SCRUM-127), the stage gates Enter-AR on the
 * launch decision, falls back to the inline web diorama with progress
 * preserved, emits challenge telemetry, and saves/restores
 * checkpoints across close or drop. Guides (SCRUM-200) render with
 * the same identity text the web challenge page shows.
 */
export function XRFixtureStage(props: XRFixtureStageProps) {
  const { attemptId, stageVersionId, challengeIndex, guides } = props;
  const linked = attemptId !== undefined && stageVersionId !== undefined;
  const challengeNo = challengeIndex ?? 1;
  const manager =
    guides?.find((guide) => guide.role === "guide") ?? guides?.[0] ?? null;

  const mountRef = useRef<HTMLDivElement | null>(null);
  const handleRef = useRef<FixtureHandle | null>(null);
  const queueRef = useRef<TelemetryQueue | null>(null);
  const launchRef = useRef<Promise<{
    route: "immersive" | "web";
    reason: string;
  }> | null>(null);
  const emittedRef = useRef(false);
  const [start] = useState(() => performance.now());
  const [reduced] = useState(() =>
    matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  // Local stash restores synchronously so first frame never waits on
  // the network; the server checkpoint wins when it arrives.
  const [stashView] = useState(() =>
    linked ? parseCheckpointView(readStashedCheckpoint(attemptId)) : null,
  );
  const [posterMs, setPosterMs] = useState<number | null>(null);
  const [frameMs, setFrameMs] = useState<number | null>(null);
  const [webgl2, setWebgl2] = useState<boolean | null>(null);
  const [xr, setXr] = useState<XRSupport | null>(null);
  const [session, setSession] = useState<SessionState>({ kind: "checking" });
  const [error, setError] = useState<string | null>(null);
  const [launch, setLaunch] = useState<{
    route: "immersive" | "web";
    reason: string;
  } | null>(null);
  const [launchFailed, setLaunchFailed] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [telemetrySent, setTelemetrySent] = useState<number | null>(null);
  // In-scene challenge + results (SCRUM-35/128): prompt, hints, goal
  // feedback, completion, and retry, all served from the attempt
  // record so verdicts report back deterministically.
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [challengeError, setChallengeError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [hintOpen, setHintOpen] = useState(false);
  const [verdicts, setVerdicts] = useState<DebriefVerdict[]>([]);
  const [submitBusy, setSubmitBusy] = useState(false);
  const [submitNote, setSubmitNote] = useState<string | null>(null);
  const [retryBusy, setRetryBusy] = useState(false);

  useEffect(() => {
    const mount = mountRef.current;
    if (mount === null) {
      return;
    }
    if (linked && queueRef.current === null) {
      const id = attemptId;
      queueRef.current = createTelemetryQueue(id, (event) =>
        api.postPlayEvent(id, event),
      );
    }
    const handle = createFixtureStage(mount, {
      startTime: start,
      reducedMotion: reduced,
      initialView: stashView,
      manager,
      callbacks: {
        onFirstFrame: (ms) => {
          setFrameMs(ms);
          const queue = queueRef.current;
          if (linked && queue !== null && !emittedRef.current) {
            emittedRef.current = true;
            queue.emit(STAGE_LOADED_VERB, {
              object_type: "stage",
              object_ref: String(stageVersionId),
              payload: { renderer: "web" },
            });
            void queue
              .flush()
              .then(() => setTelemetrySent(queue.sentCount()));
          }
        },
        onError: (msg) => setError(msg),
        onSessionChange: (presenting, detail) =>
          setSession(
            presenting
              ? { kind: "presenting" }
              : detail === "inline"
                ? { kind: "ready" }
                : { kind: "failed", reason: detail },
          ),
      },
    });
    handleRef.current = handle;
    const gl2 = handle.info().webgl2;
    setWebgl2(gl2);

    let cancelled = false;
    async function wire(): Promise<void> {
      const support = await probeXR();
      if (cancelled) {
        return;
      }
      setXr(support);
      let route: "immersive" | "web" | null = null;
      if (linked) {
        // One launch decision per stage instance: StrictMode
        // remounts await the same POST instead of logging twice.
        if (launchRef.current === null) {
          launchRef.current = api.decideLaunch(attemptId, {
            stage_version_id: stageVersionId,
            capabilities: collectCapabilities(support, {
              webgl2: gl2,
              touchPoints: navigator.maxTouchPoints,
            }),
          });
        }
        try {
          const decision = await launchRef.current;
          if (!cancelled) {
            route = decision.route;
            setLaunch({ route: decision.route, reason: decision.reason });
          }
        } catch {
          if (!cancelled) {
            setLaunchFailed(true);
          }
        }
        try {
          const found = await api.latestCheckpoint(attemptId);
          if (cancelled) {
            return;
          }
          const view = parseCheckpointView(found.checkpoint.state);
          if (view !== null) {
            handle.restoreView(view);
          }
          stashCheckpoint(attemptId, found.checkpoint.state);
          setProgress(
            `progress: resumed from checkpoint ${found.checkpoint.checkpoint_sequence}`,
          );
        } catch (exc: unknown) {
          if (cancelled) {
            return;
          }
          if (exc instanceof ApiError && exc.status === 404) {
            setProgress(
              stashView === null
                ? "progress: fresh start"
                : "progress: restored local progress",
            );
          } else {
            setProgress(
              stashView === null
                ? "progress: resume unavailable"
                : "progress: restored local progress",
            );
          }
        }
      }
      if (cancelled) {
        return;
      }
      const gate = gateImmersive(support, route);
      setSession(
        gate.allowed
          ? { kind: "ready" }
          : { kind: "unavailable", reason: gate.reason },
      );
    }
    void wire();

    // Closing or dropping the tab persists progress; a plain
    // React unmount only stashes locally so StrictMode remounts
    // never log phantom checkpoints before resume reads.
    function onPageHide(): void {
      if (!linked) {
        return;
      }
      const state = buildCheckpointState("web", handle.snapshotView());
      stashCheckpoint(attemptId, state);
      api
        .saveCheckpoint(attemptId, {
          stage_version_id: stageVersionId,
          state,
        })
        .catch(() => undefined);
    }
    addEventListener("pagehide", onPageHide);
    return () => {
      cancelled = true;
      removeEventListener("pagehide", onPageHide);
      if (linked) {
        stashCheckpoint(
          attemptId,
          buildCheckpointState("web", handle.snapshotView()),
        );
      }
      handle.dispose();
      handleRef.current = null;
    };
    // Mount-only wiring: StrictMode remounts must reuse the guarded
    // launch/telemetry refs, not re-fire them.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [start, reduced]);

  useEffect(() => {
    if (!linked) {
      return;
    }
    // Capture narrowed ids: narrowing does not reach the closure.
    const id = attemptId;
    let cancelled = false;
    async function loadChallenge(): Promise<void> {
      try {
        const [found, debrief] = await Promise.all([
          api.challenge(id, challengeNo),
          api.debrief(id),
        ]);
        if (cancelled) {
          return;
        }
        setChallenge(found.challenge);
        setSelected(
          found.challenge.goals
            .filter((goal) => goal.answered)
            .map((goal) => goal.key),
        );
        setVerdicts(debrief.debrief.verdicts);
        setChallengeError(null);
      } catch (exc: unknown) {
        if (cancelled) {
          return;
        }
        setChallengeError(
          exc instanceof Error ? exc.message : "Could not load.",
        );
      }
    }
    void loadChallenge();
    return () => {
      cancelled = true;
    };
  }, [linked, attemptId, stageVersionId, challengeNo]);

  // Floating 3D prompt follows the served challenge (SCRUM-128).
  useEffect(() => {
    handleRef.current?.setPrompt(
      challenge === null ? null : `${challenge.stage}: ${challenge.title}`,
    );
  }, [challenge]);

  async function submitInScene(): Promise<void> {
    if (!linked || challenge === null) {
      return;
    }
    setSubmitBusy(true);
    setSubmitNote(null);
    try {
      await api.answerChallenge(attemptId, challengeNo, {
        goals: selected,
        note: "in-scene",
      });
      queueRef.current?.emit("challenge-answered", {
        object_type: "challenge",
        object_ref: String(challenge.challenge_version_id),
        payload: { goals: selected },
      });
      const [found, debrief] = await Promise.all([
        api.challenge(attemptId, challengeNo),
        api.debrief(attemptId),
      ]);
      setChallenge(found.challenge);
      setVerdicts(debrief.debrief.verdicts);
      setSubmitNote("Answer recorded.");
    } catch (exc: unknown) {
      setSubmitNote(exc instanceof Error ? exc.message : "Submit failed.");
    } finally {
      setSubmitBusy(false);
    }
  }

  function showHint(): void {
    if (!linked || challenge === null) {
      return;
    }
    setHintOpen(true);
    queueRef.current?.emit("hint-requested", {
      object_type: "challenge",
      object_ref: String(challenge.challenge_version_id),
      payload: {},
    });
  }

  async function retryInScene(): Promise<void> {
    if (!linked) {
      return;
    }
    setRetryBusy(true);
    try {
      const result = await api.retryAttempt(attemptId);
      window.location.href =
        `/xr-fixture?attempt=${result.attempt_id}` +
        `&stage=${stageVersionId}&challenge=${challengeNo}`;
    } catch (exc: unknown) {
      setSubmitNote(exc instanceof Error ? exc.message : "Retry failed.");
      setRetryBusy(false);
    }
  }

  async function saveProgress(): Promise<void> {
    const handle = handleRef.current;
    if (handle === null || !linked) {
      return;
    }
    const state = buildCheckpointState("web", handle.snapshotView());
    stashCheckpoint(attemptId, state);
    try {
      const saved = await api.saveCheckpoint(attemptId, {
        stage_version_id: stageVersionId,
        state,
      });
      setProgress(
        `progress: saved checkpoint ${saved.checkpoint_sequence}`,
      );
    } catch {
      setProgress("progress: saved locally (will sync)");
    }
  }

  async function startAR(): Promise<void> {
    const handle = handleRef.current;
    if (handle === null) {
      return;
    }
    setSession({ kind: "starting" });
    try {
      await handle.enterAR();
    } catch (exc: unknown) {
      setSession({
        kind: "failed",
        reason: exc instanceof Error ? exc.message : String(exc),
      });
    }
  }

  const verdict = (ms: number | null): string =>
    ms === null
      ? "…"
      : `${Math.round(ms)}ms (target ≤${POSTER_TARGET_MS}ms) ` +
        (ms <= POSTER_TARGET_MS ? "PASS" : "FAIL");

  const buttonLabel =
    session.kind === "checking" || session.kind === "starting"
      ? "Checking XR…"
      : session.kind === "ready"
        ? "Enter AR"
        : session.kind === "presenting"
          ? "In AR — exit on device"
          : session.reason;
  const sessionLine =
    session.kind === "presenting"
      ? "session: immersive-ar"
      : session.kind === "failed"
        ? `session: failed (${session.reason})`
        : "session: inline";

  const fallback =
    linked &&
    xr !== null &&
    (launch?.route === "web" || !xr.ar || launchFailed);
  // Served challenge guides win when linked; the prop covers the
  // unlinked fixture and story-injected identity (SCRUM-200).
  const effectiveGuides = guides ?? challenge?.guides ?? [];
  const guideNames = effectiveGuides.map((guide) => guide.name).join(", ");
  const complete =
    challenge !== null &&
    challenge.goals.length > 0 &&
    challenge.goals.every((goal) => goal.answered);
  const passedCount = verdicts.filter(
    (verdict) => verdict.passed === true,
  ).length;
  const remaining =
    challenge?.goals
      .filter((goal) => !selected.includes(goal.key))
      .map((goal) => goal.key) ?? [];

  return (
    <>
      {error !== null && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <div className="xr-stage">
        <div className="xr-canvas" ref={mountRef} aria-label="Fixture stage viewport" />
        <img
          className={frameMs === null ? "xr-poster" : "xr-poster gone"}
          src={POSTER_SRC}
          alt="Volcano poster"
          onLoad={() => setPosterMs(performance.now() - start)}
        />
        <div className="xr-hud xr-hud-title">
          <h1>XR Fixture — Volcano</h1>
          <p>poster: {verdict(posterMs)}</p>
          <p>first frame: {verdict(frameMs)}</p>
          <p>{sessionLine}</p>
          {linked && (
            <p>
              launch:{" "}
              {launch === null
                ? launchFailed
                  ? "check failed"
                  : "…"
                : `${launch.route} (${launch.reason})`}
            </p>
          )}
          {linked && progress !== null && <p>{progress}</p>}
          {linked && (
            <p>telemetry: {telemetrySent === null ? "…" : telemetrySent} sent</p>
          )}
        </div>
        {effectiveGuides.length > 0 && (
          <div className="xr-hud xr-hud-guide">
            <p>Guide: {guideNames}</p>
          </div>
        )}
        {fallback && (
          <div className="xr-hud xr-hud-fallback">
            <p>Web fallback — progress preserved.</p>
            {launch !== null && <p>{launch.reason}</p>}
          </div>
        )}
        {linked && (
          <div className="xr-hud xr-hud-challenge">
            {challenge === null ? (
              <p>{challengeError ?? "Loading challenge…"}</p>
            ) : (
              <>
                <p>
                  <strong>
                    {challenge.stage}: {challenge.title}
                  </strong>
                </p>
                <p>
                  Challenge {challenge.index} of {challenge.total}
                </p>
                {challenge.goals.map((goal) => {
                  const verdict = verdicts.find(
                    (row) => row.goal === goal.key,
                  );
                  return (
                    <label key={goal.key}>
                      <input
                        type="checkbox"
                        checked={selected.includes(goal.key)}
                        disabled={submitBusy || challenge.preview}
                        onChange={(event) => {
                          const checked = event.target.checked;
                          setSelected((current) =>
                            checked
                              ? [...current, goal.key]
                              : current.filter((key) => key !== goal.key),
                          );
                        }}
                      />{" "}
                      {goal.key}
                      {goal.answered && " ✓"}
                      {verdict !== undefined && (
                        <>
                          {" "}
                          <span
                            className={`pill ${verdict.passed ? "approved" : "rejected"}`}
                          >
                            {verdict.passed ? "pass" : "fail"}
                          </span>
                        </>
                      )}
                    </label>
                  );
                })}
                <div>
                  <button type="button" onClick={showHint}>
                    Hint
                  </button>{" "}
                  <button
                    type="button"
                    disabled={submitBusy || challenge.preview}
                    onClick={() => void submitInScene()}
                  >
                    Complete in scene
                  </button>
                </div>
                {hintOpen && (
                  <p>
                    Hint — Guide: {guideNames || "—"}. Find:{" "}
                    {remaining.length > 0 ? remaining.join(", ") : "all done"}.
                  </p>
                )}
                {submitNote !== null && <p>{submitNote}</p>}
                {challenge.preview && (
                  <p>Previewing as staff — submitting is disabled.</p>
                )}
                {complete && (
                  <div className="xr-complete">
                    <p>
                      Stage complete — {passedCount} of{" "}
                      {challenge.goals.length} passed.
                    </p>
                    <button
                      type="button"
                      disabled={retryBusy || challenge.preview}
                      onClick={() => void retryInScene()}
                    >
                      Retry stage
                    </button>{" "}
                    <a
                      href={`/play/attempt/${challenge.attempt_id}/debrief`}
                    >
                      See results
                    </a>
                  </div>
                )}
              </>
            )}
          </div>
        )}
        <div className="xr-hud xr-hud-caps">
          <table>
            <tbody>
              <tr>
                <td>webgl2</td>
                <td>{webgl2 === null ? "…" : String(webgl2)}</td>
              </tr>
              <tr>
                <td>webxr</td>
                <td>{xr === null ? "…" : String(xr.hasXR)}</td>
              </tr>
              <tr>
                <td>immersive-ar</td>
                <td>{xr === null ? "…" : String(xr.ar)}</td>
              </tr>
              <tr>
                <td>immersive-vr</td>
                <td>{xr === null ? "…" : String(xr.vr)}</td>
              </tr>
              <tr>
                <td>pixel ratio</td>
                <td>{devicePixelRatio}</td>
              </tr>
              <tr>
                <td>touch points</td>
                <td>{navigator.maxTouchPoints}</td>
              </tr>
            </tbody>
          </table>
          {linked && (
            <button type="button" onClick={() => void saveProgress()}>
              Save progress
            </button>
          )}
        </div>
        <button
          type="button"
          className="xr-ar"
          disabled={session.kind !== "ready"}
          onClick={() => void startAR()}
        >
          {buttonLabel}
        </button>
      </div>
    </>
  );
}
