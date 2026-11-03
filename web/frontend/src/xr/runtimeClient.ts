/**
 * Immersive runtime client (SCRUM-127): capability reporting,
 * challenge telemetry, and checkpoint save/resume helpers shared by
 * the XR stage. Framework-free like fixtureScene; the React wrapper
 * owns all DOM.
 *
 * Telemetry follows the experience_event contract: every emission
 * carries a client_event_id idempotency key, a verb, an
 * object_type/object_ref pair, and a payload object. Checkpoints
 * follow the session_checkpoint contract: the server is the source
 * of truth and a local stash only covers offline close/drop gaps.
 */
import type { XRSupport } from "./fixtureScene";

/** Guide identity, same shape as the web challenge view (SCRUM-200). */
export interface GuideIdentity {
  name: string;
  role: string;
}

export interface OrbitView {
  theta: number;
  phi: number;
  radius: number;
}

export const CHECKPOINT_SCHEMA_VERSION = 1;
export const STAGE_LOADED_VERB = "stage-loaded";

/** Capability keys reported to the launch endpoint. */
export function collectCapabilities(
  support: XRSupport,
  info: { webgl2: boolean; touchPoints: number },
): string[] {
  const caps: string[] = [];
  if (info.webgl2) {
    caps.push("webgl2");
  }
  if (support.hasXR) {
    caps.push("webxr");
  }
  if (support.ar) {
    caps.push("immersive-ar");
  }
  if (support.vr) {
    caps.push("immersive-vr");
  }
  if (info.touchPoints > 0) {
    caps.push("touch");
  }
  return caps;
}

/** Gate the Enter-AR button on probe support plus launch routing. */
export function gateImmersive(
  support: XRSupport,
  route: "immersive" | "web" | null,
): { allowed: boolean; reason: string } {
  if (route === "web") {
    return { allowed: false, reason: "Routed to web fallback" };
  }
  if (!support.ar) {
    return {
      allowed: false,
      reason: support.hasXR ? "AR unavailable" : "No WebXR here",
    };
  }
  return { allowed: true, reason: "ready" };
}

/** Idempotency key for one telemetry event. Never throws. */
export function newClientEventId(): string {
  try {
    if (
      typeof crypto !== "undefined" &&
      typeof crypto.randomUUID === "function"
    ) {
      return crypto.randomUUID();
    }
  } catch {
    /* fall through to the timestamp fallback */
  }
  return (
    `evt-${Date.now().toString(36)}-` +
    Math.floor(Math.random() * 0xffffffff).toString(36)
  );
}

export interface TelemetryEnvelope {
  client_event_id: string;
  verb: string;
  object_type: string;
  object_ref: string;
  payload: Record<string, unknown>;
}

export interface TelemetryQueue {
  emit: (
    verb: string,
    opts?: {
      object_type?: string;
      object_ref?: string;
      payload?: Record<string, unknown>;
    },
  ) => void;
  sentCount: () => number;
  pendingCount: () => number;
  flush: () => Promise<void>;
}

function outboxKey(attemptId: number): string {
  return `xr-telemetry:${attemptId}`;
}

function loadOutbox(attemptId: number): TelemetryEnvelope[] {
  try {
    const raw = localStorage.getItem(outboxKey(attemptId));
    if (raw === null) {
      return [];
    }
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter(
      (entry): entry is TelemetryEnvelope =>
        typeof entry === "object" &&
        entry !== null &&
        typeof (entry as TelemetryEnvelope).client_event_id === "string" &&
        typeof (entry as TelemetryEnvelope).verb === "string",
    );
  } catch {
    return [];
  }
}

/**
 * Ordered telemetry queue with a localStorage outbox: emissions are
 * fire-and-forget, retried in order, and replayed after a close or
 * drop. Server-side idempotency (duplicate client_event_id) makes
 * replays safe.
 */
export function createTelemetryQueue(
  attemptId: number,
  post: (event: TelemetryEnvelope) => Promise<unknown>,
): TelemetryQueue {
  const outbox = loadOutbox(attemptId);
  let sent = 0;
  // Flushes serialize on a chain (never a dropped early return) so
  // every caller observes the posts it waited for.
  let tail: Promise<void> = Promise.resolve();

  function persist(): void {
    try {
      localStorage.setItem(outboxKey(attemptId), JSON.stringify(outbox));
    } catch {
      /* private mode keeps the in-memory outbox only */
    }
  }

  async function run(): Promise<void> {
    while (outbox.length > 0) {
      const next = outbox[0];
      try {
        await post(next);
      } catch {
        persist();
        return;
      }
      outbox.shift();
      sent += 1;
    }
    persist();
  }

  function flush(): Promise<void> {
    tail = tail.then(run);
    return tail;
  }

  return {
    emit: (verb, opts) => {
      outbox.push({
        client_event_id: newClientEventId(),
        verb,
        object_type: opts?.object_type ?? "",
        object_ref: opts?.object_ref ?? "",
        payload: opts?.payload ?? {},
      });
      persist();
      void flush();
    },
    sentCount: () => sent,
    pendingCount: () => outbox.length,
    flush: () => flush(),
  };
}

/** Checkpoint state the server stores opaquely. */
export function buildCheckpointState(
  renderer: "web" | "immersive",
  view: OrbitView,
): Record<string, unknown> {
  return {
    renderer,
    schema_version: CHECKPOINT_SCHEMA_VERSION,
    view: { theta: view.theta, phi: view.phi, radius: view.radius },
  };
}

/** Read the orbit view back out of a checkpoint state, if valid. */
export function parseCheckpointView(state: unknown): OrbitView | null {
  if (typeof state !== "object" || state === null) {
    return null;
  }
  const view = (state as { view?: unknown }).view;
  if (typeof view !== "object" || view === null) {
    return null;
  }
  const { theta, phi, radius } = view as Record<string, unknown>;
  if (
    typeof theta !== "number" ||
    typeof phi !== "number" ||
    typeof radius !== "number" ||
    !Number.isFinite(theta) ||
    !Number.isFinite(phi) ||
    !Number.isFinite(radius)
  ) {
    return null;
  }
  return { theta, phi, radius };
}

function stashKey(attemptId: number): string {
  return `xr-checkpoint:${attemptId}`;
}

/** Stash progress locally so a close/drop loses nothing offline. */
export function stashCheckpoint(
  attemptId: number,
  state: Record<string, unknown>,
): void {
  try {
    localStorage.setItem(stashKey(attemptId), JSON.stringify(state));
  } catch {
    /* private mode: server checkpoints still apply */
  }
}

export function readStashedCheckpoint(
  attemptId: number,
): Record<string, unknown> | null {
  try {
    const raw = localStorage.getItem(stashKey(attemptId));
    if (raw === null) {
      return null;
    }
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) {
      return null;
    }
    return parsed as Record<string, unknown>;
  } catch {
    return null;
  }
}
