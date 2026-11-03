/**
 * Fixture volcano stage for the immersive spike (SCRUM-22).
 *
 * Framework-free three.js module: builds the diorama, runs the
 * XR-compatible animation loop, and tears everything down on dispose
 * (StrictMode mounts twice; both passes must work). The React wrapper
 * lives in components/XRFixtureStage; all DOM outside the canvas is
 * owned there.
 */
import * as THREE from "three";
import type { GuideIdentity, OrbitView } from "./runtimeClient";

export interface FixtureCallbacks {
  onFirstFrame: (msSinceStart: number) => void;
  onError: (message: string) => void;
  onSessionChange: (presenting: boolean, detail: string) => void;
}

export interface FixtureHandle {
  enterAR: () => Promise<void>;
  dispose: () => void;
  info: () => { webgl2: boolean };
  snapshotView: () => OrbitView;
  restoreView: (view: OrbitView) => void;
  /** Floating in-scene challenge prompt (SCRUM-128); null clears it. */
  setPrompt: (text: string | null) => void;
}

/** Default orbit view; checkpoints restore into this shape. */
export const DEFAULT_VIEW: OrbitView = { theta: 0.65, phi: 1.08, radius: 27 };

export interface XRSupport {
  hasXR: boolean;
  ar: boolean;
  vr: boolean;
}

const COLORS = {
  sky: 0x7fb2e5,
  horizon: 0xdcebf5,
  basalt: 0x3a3f44,
  lava: 0xff5a1f,
  smoke: 0xcfd4d9,
};

function canvasTexture(
  size: number,
  draw: (ctx: CanvasRenderingContext2D, size: number) => void,
): THREE.CanvasTexture {
  const cv = document.createElement("canvas");
  cv.width = cv.height = size;
  const ctx = cv.getContext("2d");
  if (ctx === null) {
    throw new Error("2d canvas unavailable");
  }
  draw(ctx, size);
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function speckle(
  ctx: CanvasRenderingContext2D,
  size: number,
  n: number,
  colors: string[],
  rMin: number,
  rMax: number,
): void {
  for (let i = 0; i < n; i++) {
    ctx.fillStyle = colors[(Math.random() * colors.length) | 0];
    ctx.globalAlpha = 0.25 + Math.random() * 0.5;
    const r = rMin + Math.random() * (rMax - rMin);
    ctx.beginPath();
    ctx.arc(Math.random() * size, Math.random() * size, r, 0, 7);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function textSprite(text: string): THREE.Sprite {
  const cv = document.createElement("canvas");
  cv.width = 256;
  cv.height = 64;
  const ctx = cv.getContext("2d");
  if (ctx === null) {
    throw new Error("2d canvas unavailable");
  }
  ctx.fillStyle = "rgba(10,14,18,.72)";
  ctx.beginPath();
  ctx.roundRect(4, 6, 248, 52, 12);
  ctx.fill();
  ctx.font = "600 30px system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#ffd9a8";
  ctx.fillText(text, 128, 34);
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: tex, transparent: true }),
  );
  sprite.scale.set(4.4, 1.1, 1);
  return sprite;
}

/** Probe WebXR support without starting a session. Never throws. */
export async function probeXR(): Promise<XRSupport> {
  const out: XRSupport = { hasXR: false, ar: false, vr: false };
  if (!("xr" in navigator) || navigator.xr === undefined) {
    return out;
  }
  out.hasXR = true;
  try {
    out.ar = await navigator.xr.isSessionSupported("immersive-ar");
  } catch {
    out.ar = false;
  }
  try {
    out.vr = await navigator.xr.isSessionSupported("immersive-vr");
  } catch {
    out.vr = false;
  }
  return out;
}

const CONE_PROFILE: Array<[number, number]> = [
  [9.6, 0], [8.7, 1.2], [7.0, 2.8], [5.4, 4.2], [4.1, 5.4],
  [3.4, 6.2], [2.6, 6.6], [2.1, 6.35], [1.6, 5.9],
];

const SMOKE_N = 70;

export function createFixtureStage(
  container: HTMLElement,
  opts: {
    startTime: number;
    reducedMotion: boolean;
    callbacks: FixtureCallbacks;
    /** Restored orbit view from a checkpoint (SCRUM-127). */
    initialView?: OrbitView | null;
    /** Guide rendered in-scene with web identity (SCRUM-200). */
    manager?: GuideIdentity | null;
    /** Floating challenge prompt above the diorama (SCRUM-128). */
    prompt?: string | null;
  },
): FixtureHandle {
  const { startTime, reducedMotion, callbacks, initialView, manager } = opts;
  let renderer: THREE.WebGLRenderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true });
  } catch (exc: unknown) {
    const message = exc instanceof Error ? exc.message : String(exc);
    callbacks.onError(`WebGL unavailable: ${message}`);
    return {
      enterAR: () => Promise.reject(new Error("no renderer")),
      dispose: () => undefined,
      info: () => ({ webgl2: false }),
      snapshotView: () => ({ ...DEFAULT_VIEW }),
      restoreView: () => undefined,
      setPrompt: () => undefined,
    };
  }
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.xr.enabled = true;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(COLORS.horizon, 45, 150);
  const camera = new THREE.PerspectiveCamera(
    55, container.clientWidth / Math.max(1, container.clientHeight), 0.1, 400,
  );

  const sun = new THREE.DirectionalLight(0xfff2df, 2.4);
  sun.position.set(24, 34, 14);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  sun.shadow.camera.left = -20;
  sun.shadow.camera.right = 20;
  sun.shadow.camera.top = 20;
  sun.shadow.camera.bottom = -20;
  sun.shadow.camera.far = 90;
  scene.add(sun, new THREE.HemisphereLight(0xbcd4ee, 0x3a352f, 0.9));
  const craterGlow = new THREE.PointLight(0xff6a2a, 40, 30, 2);
  craterGlow.position.set(0, 7.4, 0);
  scene.add(craterGlow);

  const skyTex = canvasTexture(512, (ctx, s) => {
    const g = ctx.createLinearGradient(0, 0, 0, s);
    g.addColorStop(0, "#5d97d6");
    g.addColorStop(0.55, "#7fb2e5");
    g.addColorStop(0.72, "#dcebf5");
    g.addColorStop(1, "#3a3f44");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, s, s);
  });
  scene.add(new THREE.Mesh(
    new THREE.SphereGeometry(180, 24, 16),
    new THREE.MeshBasicMaterial({ map: skyTex, side: THREE.BackSide, fog: false }),
  ));

  const groundTex = canvasTexture(512, (ctx, s) => {
    const g = ctx.createRadialGradient(s / 2, s / 2, s * 0.05, s / 2, s / 2, s * 0.52);
    g.addColorStop(0, "#2e2b27");
    g.addColorStop(0.45, "#4a4640");
    g.addColorStop(1, "#33302b");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, s, s);
    speckle(ctx, s, 900, ["#5a544c", "#242220", "#6b6257"], 1, 4);
  });
  const ground = new THREE.Mesh(
    new THREE.CircleGeometry(38, 48),
    new THREE.MeshStandardMaterial({
      map: groundTex, bumpMap: groundTex, bumpScale: 0.4, roughness: 0.95,
    }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);

  const strataTex = canvasTexture(512, (ctx, s) => {
    ctx.fillStyle = "#3a3f44";
    ctx.fillRect(0, 0, s, s);
    const bands = ["#46413a", "#33302b", "#544e45", "#2e2b27", "#5a544c"];
    for (let i = 0; i < 26; i++) {
      ctx.fillStyle = bands[i % bands.length];
      ctx.globalAlpha = 0.55;
      ctx.fillRect(0, (i / 26) * s + Math.random() * 6, s, 5 + Math.random() * 12);
    }
    ctx.globalAlpha = 1;
    speckle(ctx, s, 500, ["#242220", "#6b6257"], 1, 3);
  });
  const cone = new THREE.Mesh(
    new THREE.LatheGeometry(
      CONE_PROFILE.map(([x, y]) => new THREE.Vector2(x, y)), 40,
    ),
    new THREE.MeshStandardMaterial({
      map: strataTex, bumpMap: strataTex, bumpScale: 0.5, roughness: 0.9,
    }),
  );
  cone.castShadow = cone.receiveShadow = true;
  scene.add(cone);

  const lavaMat = new THREE.MeshStandardMaterial({
    color: 0x1a0c06, emissive: COLORS.lava, emissiveIntensity: 2.2, roughness: 0.6,
  });
  const lava = new THREE.Mesh(new THREE.CircleGeometry(1.7, 28), lavaMat);
  lava.rotation.x = -Math.PI / 2;
  lava.position.y = 6.15;
  scene.add(lava);
  const flank = new THREE.Mesh(
    new THREE.ConeGeometry(1.2, 1.7, 18),
    new THREE.MeshStandardMaterial({ color: COLORS.basalt, roughness: 0.9 }),
  );
  flank.position.set(5.6, 2.35, 2.8);
  flank.castShadow = flank.receiveShadow = true;
  scene.add(flank);
  scene.add(new THREE.Mesh(
    new THREE.TubeGeometry(new THREE.QuadraticBezierCurve3(
      new THREE.Vector3(5.2, 3.1, 2.6),
      new THREE.Vector3(6.4, 1.8, 3.4),
      new THREE.Vector3(7.6, 0.4, 4.2),
    ), 20, 0.14, 8),
    new THREE.MeshStandardMaterial({
      color: 0x1a0c06, emissive: 0xff3d00, emissiveIntensity: 1.8,
    }),
  ));

  const rockMat = new THREE.MeshStandardMaterial({
    color: 0x2e3236, roughness: 0.95, flatShading: true,
  });
  [[-12, 0.7, 6, 1.4], [11, 0.5, -7, 1.0], [-7, 0.4, -12, 0.8]].forEach(
    ([x, y, z, r], i) => {
      const rock = new THREE.Mesh(new THREE.IcosahedronGeometry(r, 0), rockMat);
      rock.position.set(x, y, z);
      rock.rotation.set(i * 1.3, i * 2.1, i * 0.7);
      rock.scale.y = 0.72;
      rock.castShadow = rock.receiveShadow = true;
      scene.add(rock);
    });
  const farMat = new THREE.MeshBasicMaterial({ color: 0x8b98a8 });
  [[-70, -60, 26, 30], [75, -40, 20, 24]].forEach(([x, z, r, h]) => {
    const far = new THREE.Mesh(new THREE.ConeGeometry(r, h, 7), farMat);
    far.position.set(x, h / 2 - 2, z);
    scene.add(far);
  });

  const craterTag = textSprite("crater");
  craterTag.position.set(0, 8.6, 0);
  const ventTag = textSprite("vent");
  ventTag.position.set(7.6, 4.6, 4.2);
  scene.add(craterTag, ventTag);

  // Manager guide presence (SCRUM-200): a marker plus a name
  // placard carrying the same identity the web challenge view
  // shows. Static by design; motion belongs to a later slice.
  if (manager !== null && manager !== undefined) {
    const marker = new THREE.Mesh(
      new THREE.OctahedronGeometry(0.55),
      new THREE.MeshStandardMaterial({
        color: 0x2c5c3f, emissive: 0x1d3d2a, emissiveIntensity: 0.8,
        roughness: 0.5,
      }),
    );
    marker.position.set(-6.2, 3.4, 6.4);
    marker.castShadow = true;
    const tag = textSprite(manager.name);
    tag.position.set(-6.2, 5.0, 6.4);
    scene.add(marker, tag);
  }

  const smokeGeo = new THREE.BufferGeometry();
  const smokePos = new Float32Array(SMOKE_N * 3);
  const smokeSeed = new Float32Array(SMOKE_N);
  for (let i = 0; i < SMOKE_N; i++) {
    smokePos[i * 3] = (Math.random() - 0.5) * 2.4;
    smokePos[i * 3 + 1] = 6.6 + Math.random() * 9;
    smokePos[i * 3 + 2] = (Math.random() - 0.5) * 2.4;
    smokeSeed[i] = Math.random();
  }
  smokeGeo.setAttribute("position", new THREE.BufferAttribute(smokePos, 3));
  const puffTex = canvasTexture(64, (ctx, s) => {
    const g = ctx.createRadialGradient(s / 2, s / 2, 1, s / 2, s / 2, s / 2);
    g.addColorStop(0, "rgba(255,255,255,.9)");
    g.addColorStop(0.5, "rgba(255,255,255,.35)");
    g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, s, s);
  });
  scene.add(new THREE.Points(smokeGeo, new THREE.PointsMaterial({
    size: 2.2, map: puffTex, transparent: true, opacity: 0.5,
    color: COLORS.smoke, depthWrite: false, sizeAttenuation: true,
  })));

  const orbit = {
    theta: initialView?.theta ?? DEFAULT_VIEW.theta,
    phi: initialView?.phi ?? DEFAULT_VIEW.phi,
    radius: initialView?.radius ?? DEFAULT_VIEW.radius,
    target: new THREE.Vector3(0, 3.6, 0),
  };
  let lastTouch = 0;
  function applyCamera(): void {
    camera.position.set(
      orbit.target.x + orbit.radius * Math.sin(orbit.phi) * Math.sin(orbit.theta),
      orbit.target.y + orbit.radius * Math.cos(orbit.phi),
      orbit.target.z + orbit.radius * Math.sin(orbit.phi) * Math.cos(orbit.theta),
    );
    camera.lookAt(orbit.target);
  }
  applyCamera();

  const el = renderer.domElement;
  el.style.touchAction = "none";
  el.style.display = "block";
  el.style.width = "100%";
  el.style.height = "100%";
  let dragging = false;
  let px = 0;
  let py = 0;
  let pinchD = 0;
  const onPointerDown = (ev: PointerEvent): void => {
    dragging = true;
    px = ev.clientX;
    py = ev.clientY;
    try {
      el.setPointerCapture(ev.pointerId);
    } catch {
      /* synthetic or already-released pointers carry on without capture */
    }
  };
  const onPointerMove = (ev: PointerEvent): void => {
    if (!dragging || renderer.xr.isPresenting) return;
    orbit.theta -= (ev.clientX - px) * 0.005;
    orbit.phi = Math.min(1.45, Math.max(0.35, orbit.phi - (ev.clientY - py) * 0.004));
    px = ev.clientX;
    py = ev.clientY;
    lastTouch = performance.now();
    applyCamera();
  };
  const onPointerUp = (): void => { dragging = false; };
  const onWheel = (ev: WheelEvent): void => {
    ev.preventDefault();
    orbit.radius = Math.min(60, Math.max(12, orbit.radius * (1 + ev.deltaY * 0.001)));
    lastTouch = performance.now();
    applyCamera();
  };
  const onTouchMove = (ev: TouchEvent): void => {
    if (ev.touches.length !== 2) return;
    ev.preventDefault();
    const d = Math.hypot(
      ev.touches[0].clientX - ev.touches[1].clientX,
      ev.touches[0].clientY - ev.touches[1].clientY);
    if (pinchD > 0) {
      orbit.radius = Math.min(60, Math.max(12, orbit.radius * (pinchD / d)));
      lastTouch = performance.now();
      applyCamera();
    }
    pinchD = d;
  };
  const onTouchEnd = (): void => { pinchD = 0; };
  const onResize = (): void => {
    camera.aspect = container.clientWidth / Math.max(1, container.clientHeight);
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
  };
  el.addEventListener("pointerdown", onPointerDown);
  el.addEventListener("pointermove", onPointerMove);
  el.addEventListener("pointerup", onPointerUp);
  el.addEventListener("pointercancel", onPointerUp);
  el.addEventListener("wheel", onWheel, { passive: false });
  el.addEventListener("touchmove", onTouchMove, { passive: false });
  el.addEventListener("touchend", onTouchEnd);
  addEventListener("resize", onResize);

  async function enterAR(): Promise<void> {
    if (!("xr" in navigator) || navigator.xr === undefined) {
      throw new Error("WebXR unavailable");
    }
    const session = await navigator.xr.requestSession("immersive-ar", {
      requiredFeatures: ["local-floor"],
      optionalFeatures: ["hit-test"],
    });
    session.addEventListener("end", () => {
      callbacks.onSessionChange(false, "inline");
      applyCamera();
    });
    await renderer.xr.setSession(session);
    callbacks.onSessionChange(true, "immersive-ar");
  }

  function dispose(): void {
    renderer.setAnimationLoop(null);
    removeEventListener("resize", onResize);
    scene.traverse((obj) => {
      const mesh = obj as THREE.Mesh;
      if (mesh.geometry !== undefined) {
        mesh.geometry.dispose();
      }
      const mat = (mesh as THREE.Mesh).material as THREE.Material | THREE.Material[] | undefined;
      if (Array.isArray(mat)) {
        mat.forEach((m) => m.dispose());
      } else if (mat !== undefined) {
        mat.dispose();
      }
    });
    renderer.dispose();
    el.remove();
  }

  let firstFrame = true;
  const clock = new THREE.Clock();
  renderer.setAnimationLoop(() => {
    const dt = Math.min(clock.getDelta(), 0.1);
    const t = clock.elapsedTime;
    if (!renderer.xr.isPresenting && !reducedMotion) {
      if (performance.now() - lastTouch > 4000) {
        orbit.theta += dt * 0.05;
        applyCamera();
      }
      lavaMat.emissiveIntensity = 2.2 + Math.sin(t * 3.1) * 0.35;
      const pos = smokeGeo.attributes.position;
      for (let i = 0; i < SMOKE_N; i++) {
        let y = pos.getY(i) + dt * (0.9 + smokeSeed[i]);
        if (y > 16) y = 6.6;
        pos.setY(i, y);
        pos.setX(i, pos.getX(i) + Math.sin(t * 0.8 + smokeSeed[i] * 6.3) * dt * 0.35);
      }
      pos.needsUpdate = true;
    }
    renderer.render(scene, camera);
    if (firstFrame) {
      firstFrame = false;
      callbacks.onFirstFrame(performance.now() - startTime);
    }
  });

  function snapshotView(): OrbitView {
    return { theta: orbit.theta, phi: orbit.phi, radius: orbit.radius };
  }

  function restoreView(view: OrbitView): void {
    orbit.theta = view.theta;
    orbit.phi = Math.min(1.45, Math.max(0.35, view.phi));
    orbit.radius = Math.min(60, Math.max(12, view.radius));
    applyCamera();
  }

  let promptSprite: THREE.Sprite | null = null;
  function setPrompt(text: string | null): void {
    if (promptSprite !== null) {
      scene.remove(promptSprite);
      const material = promptSprite.material as THREE.SpriteMaterial;
      material.map?.dispose();
      material.dispose();
      promptSprite = null;
    }
    if (text === null || text === "") {
      return;
    }
    promptSprite = textSprite(text);
    promptSprite.position.set(0, 11.6, 0);
    scene.add(promptSprite);
  }
  setPrompt(opts.prompt ?? null);

  return {
    enterAR,
    dispose,
    info: () => ({ webgl2: renderer.capabilities.isWebGL2 }),
    snapshotView,
    restoreView,
    setPrompt,
  };
}
