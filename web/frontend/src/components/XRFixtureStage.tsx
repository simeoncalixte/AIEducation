import { useEffect, useRef, useState } from "react";
import {
  createFixtureStage,
  probeXR,
  type FixtureHandle,
  type XRSupport,
} from "../xr/fixtureScene";

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

/**
 * Fixture volcano stage for the immersive spike (SCRUM-22): poster
 * first, then the live three.js diorama with paint timings,
 * capability report, and an Enter-AR session button. Timings measure
 * from component mount (a direct page load lands here, so mount is
 * close to navigation start).
 */
export function XRFixtureStage() {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const handleRef = useRef<FixtureHandle | null>(null);
  const [start] = useState(() => performance.now());
  const [reduced] = useState(() =>
    matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [posterMs, setPosterMs] = useState<number | null>(null);
  const [frameMs, setFrameMs] = useState<number | null>(null);
  const [webgl2, setWebgl2] = useState<boolean | null>(null);
  const [xr, setXr] = useState<XRSupport | null>(null);
  const [session, setSession] = useState<SessionState>({ kind: "checking" });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (mount === null) {
      return;
    }
    const handle = createFixtureStage(mount, {
      startTime: start,
      reducedMotion: reduced,
      callbacks: {
        onFirstFrame: (ms) => setFrameMs(ms),
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
    setWebgl2(handle.info().webgl2);
    let cancelled = false;
    void probeXR().then((support) => {
      if (cancelled) {
        return;
      }
      setXr(support);
      setSession(
        support.ar
          ? { kind: "ready" }
          : {
              kind: "unavailable",
              reason: support.hasXR ? "AR unavailable" : "No WebXR here",
            },
      );
    });
    return () => {
      cancelled = true;
      handle.dispose();
      handleRef.current = null;
    };
  }, [start, reduced]);

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
        </div>
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
