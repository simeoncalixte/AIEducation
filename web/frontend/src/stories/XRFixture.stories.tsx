import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { XRFixtureStage } from "../components/XRFixtureStage";

const meta = {
  title: "XR/Fixture",
  component: XRFixtureStage,
} satisfies Meta<typeof XRFixtureStage>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Live-server linked stage (SCRUM-127): resets the server database,
 * assigns seeded Volcanoes to Room 1, starts an attempt as sam, and
 * renders the stage linked to the pinned stage version. Mirrors the
 * Challenge stories' live setup through the API.
 */
function LinkedStage({ seedCheckpoint }: { seedCheckpoint: boolean }) {
  const [link, setLink] = useState<{
    attemptId: number;
    stageVersionId: number;
  } | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const setupRef = useRef(false);
  useEffect(() => {
    if (setupRef.current) {
      return;
    }
    setupRef.current = true;
    void (async () => {
      try {
        localStorage.clear();
        await api.testReset();
        await api.login("tess");
        const { options } = await api.assignments();
        const lesson = options.lessons.find(
          (row) => row.title === "Volcanoes",
        );
        const room = options.classrooms.find((row) =>
          row.name.includes("Room 1"),
        );
        if (lesson === undefined || room === undefined) {
          throw new Error("Seeded lesson or classroom missing.");
        }
        const { assignment_id } = await api.assign({
          lesson_id: String(lesson.id),
          classroom_id: String(room.id),
          student_id: "",
        });
        await api.login("sam");
        const { attempt_id } = await api.startAttempt(assignment_id);
        const { briefing } = await api.briefing(assignment_id);
        const pinned = briefing.stage_versions?.[0];
        if (pinned === undefined) {
          throw new Error("No pinned stage version in briefing.");
        }
        if (seedCheckpoint) {
          await api.saveCheckpoint(attempt_id, {
            stage_version_id: pinned.stage_version_id,
            state: {
              renderer: "web",
              schema_version: 1,
              view: { theta: 1.1, phi: 0.9, radius: 40 },
            },
          });
        }
        setLink({
          attemptId: attempt_id,
          stageVersionId: pinned.stage_version_id,
        });
      } catch (exc: unknown) {
        setFailed(exc instanceof Error ? exc.message : String(exc));
      }
    })();
  }, [seedCheckpoint]);
  if (failed !== null) {
    return <p role="alert">Setup failed: {failed}</p>;
  }
  if (link === null) {
    return <p>Preparing linked stage…</p>;
  }
  return (
    <XRFixtureStage
      attemptId={link.attemptId}
      stageVersionId={link.stageVersionId}
    />
  );
}

/** Fixture loads: poster, live canvas, timings, caps, AR button (SCRUM-22). */
export const FixtureLoads: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(
      canvas.getByRole("img", { name: "Volcano poster" }),
    ).toBeInTheDocument();
    await canvas.findByText(/poster: \d+ms/, {}, { timeout: 15000 });
    await canvas.findByText(/first frame: \d+ms/, {}, { timeout: 20000 });
    const el = canvasElement.querySelector("canvas");
    expect(el).not.toBeNull();
    for (const row of ["webxr", "immersive-ar", "immersive-vr"]) {
      expect(canvas.getByText(row)).toBeInTheDocument();
    }
    const button = canvas.getByRole("button");
    expect(button).toBeDisabled();
    expect(canvas.queryByRole("alert")).toBeNull();
  },
};

/** Dragging the canvas orbits without errors (SCRUM-22). */
export const OrbitDrag: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/first frame: \d+ms/, {}, { timeout: 20000 });
    const el = canvasElement.querySelector("canvas");
    expect(el).not.toBeNull();
    if (el === null) {
      return;
    }
    const rect = el.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    await userEvent.pointer([
      { target: el, coords: { x: cx, y: cy }, keys: "[MouseLeft>]" },
      { coords: { x: cx + 120, y: cy - 40 } },
      { keys: "[/MouseLeft]" },
    ]);
    expect(canvasElement.querySelector("canvas")).not.toBeNull();
    expect(canvas.queryByRole("alert")).toBeNull();
  },
};

/**
 * Linked stage without XR: launch gating routes to the inline web
 * fallback with progress preserved, and stage telemetry is acked
 * (SCRUM-127). The seed declares no scene requirements, so the
 * launch decision is immersive and the probe gates Enter-AR off.
 */
export const LinkedFallbackGating: Story = {
  render: () => <LinkedStage seedCheckpoint={false} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/first frame: \d+ms/, {}, { timeout: 60000 });
    await canvas.findByText(
      "Web fallback — progress preserved.",
      {},
      { timeout: 15000 },
    );
    await canvas.findByText(/launch: immersive/, {}, { timeout: 15000 });
    await canvas.findByText("progress: fresh start", {}, { timeout: 15000 });
    await canvas.findByText(/telemetry: 1 sent/, {}, { timeout: 15000 });
    const button = canvas.getByRole("button", {
      name: /No WebXR here|AR unavailable/,
    });
    expect(button).toBeDisabled();
    expect(canvasElement.querySelector("canvas")).not.toBeNull();
    expect(canvas.queryByRole("alert")).toBeNull();
  },
};

/**
 * Checkpoint save and resume against the live server (SCRUM-127):
 * the seeded checkpoint restores on mount, and Save progress logs
 * the next sequence.
 */
export const CheckpointSaveResume: Story = {
  render: () => <LinkedStage seedCheckpoint />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(
      "progress: resumed from checkpoint 1",
      {},
      { timeout: 60000 },
    );
    await userEvent.click(
      canvas.getByRole("button", { name: "Save progress" }),
    );
    await canvas.findByText(
      "progress: saved checkpoint 2",
      {},
      { timeout: 15000 },
    );
    expect(canvasElement.querySelector("canvas")).not.toBeNull();
    expect(canvas.queryByRole("alert")).toBeNull();
  },
};

/**
 * Manager guide without XR: the inline presentation carries the
 * same "Guide: {name}" identity text the web challenge page shows,
 * with no errors (SCRUM-200).
 */
export const ManagerInlineFallback: Story = {
  args: { guides: [{ name: "Manager", role: "guide" }] },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/first frame: \d+ms/, {}, { timeout: 20000 });
    expect(canvas.getByText("Guide: Manager")).toBeInTheDocument();
    expect(canvasElement.querySelector("canvas")).not.toBeNull();
    expect(canvas.queryByRole("alert")).toBeNull();
  },
};

/** Resolve a seeded queue row id through the live API. */
async function queueId(
  kind: "asset" | "stage" | "lesson",
  match: (row: { title: string; status: string; version_no: number }) => boolean,
): Promise<number> {
  const { queues } = await api.review();
  const row = queues[kind].find(match);
  expect(row).toBeDefined();
  return row?.id ?? 0;
}

/** Approve + publish one draft through the live API. */
async function ship(
  kind: "asset" | "stage" | "lesson",
  versionId: number,
): Promise<void> {
  await api.approve(kind, versionId, "spike proof");
  await api.publish(kind, versionId, "spike proof");
}

/**
 * Live-server linked stage with the challenge lesson published
 * (SCRUM-35/128): same setup as LinkedStage, plus shipping the
 * labeling challenge so challenge 1 serves in scene.
 */
function LinkedChallengeStage() {
  const [link, setLink] = useState<{
    attemptId: number;
    stageVersionId: number;
  } | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const setupRef = useRef(false);
  useEffect(() => {
    if (setupRef.current) {
      return;
    }
    setupRef.current = true;
    void (async () => {
      try {
        localStorage.clear();
        await api.testReset();
        await api.login("tess");
        await ship(
          "asset",
          await queueId("asset", (row) =>
            row.title.includes("Volcano Model") && row.status === "draft",
          ),
        );
        await ship(
          "asset",
          await queueId("asset", (row) =>
            row.title.includes("Label the Parts") && row.status === "draft",
          ),
        );
        await ship(
          "stage",
          await queueId("stage", (row) =>
            row.title.includes("Eruption") && row.status === "draft",
          ),
        );
        await ship(
          "lesson",
          await queueId(
            "lesson",
            (row) =>
              row.title.includes("Volcanoes") &&
              row.status === "draft" &&
              row.version_no === 3,
          ),
        );
        const { options } = await api.assignments();
        const lesson = options.lessons.find(
          (row) => row.title === "Volcanoes",
        );
        const room = options.classrooms.find((row) =>
          row.name.includes("Room 1"),
        );
        if (lesson === undefined || room === undefined) {
          throw new Error("Seeded lesson or classroom missing.");
        }
        const { assignment_id } = await api.assign({
          lesson_id: String(lesson.id),
          classroom_id: String(room.id),
          student_id: "",
        });
        await api.login("sam");
        const { attempt_id } = await api.startAttempt(assignment_id);
        const { briefing } = await api.briefing(assignment_id);
        const pinned = briefing.stage_versions?.[0];
        if (pinned === undefined) {
          throw new Error("No pinned stage version in briefing.");
        }
        setLink({
          attemptId: attempt_id,
          stageVersionId: pinned.stage_version_id,
        });
      } catch (exc: unknown) {
        setFailed(exc instanceof Error ? exc.message : String(exc));
      }
    })();
  }, []);
  if (failed !== null) {
    return <p role="alert">Setup failed: {failed}</p>;
  }
  if (link === null) {
    return <p>Preparing linked stage…</p>;
  }
  return (
    <XRFixtureStage
      attemptId={link.attemptId}
      stageVersionId={link.stageVersionId}
      challengeIndex={1}
    />
  );
}

/**
 * In-scene challenge end to end (SCRUM-35/128): poster, then the
 * served prompt with hints, goal completion in scene, verdict
 * feedback from the record, a completion screen, and a retry path.
 */
export const LinkedChallengePlay: Story = {
  render: () => <LinkedChallengeStage />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/first frame: \d+ms/, {}, { timeout: 60000 });
    await canvas.findByText("Challenge 1 of 1", {}, { timeout: 15000 });
    expect(canvas.getByText(/Label the Parts/)).toBeInTheDocument();
    expect(canvas.getByText("Guide: Manager")).toBeInTheDocument();
    await userEvent.click(canvas.getByRole("button", { name: "Hint" }));
    await canvas.findByText(/Hint — Guide: Manager/, {}, { timeout: 15000 });
    await userEvent.click(
      canvas.getByRole("checkbox", { name: "crater" }),
    );
    await userEvent.click(
      canvas.getByRole("checkbox", { name: "explain" }),
    );
    await userEvent.click(canvas.getByRole("checkbox", { name: "vent" }));
    await userEvent.click(
      canvas.getByRole("button", { name: "Complete in scene" }),
    );
    await canvas.findByText("Answer recorded.", {}, { timeout: 15000 });
    await canvas.findByText(/Stage complete/, {}, { timeout: 15000 });
    // The open explanation waits on a teacher grade, so only the two
    // deterministic verdicts count as passed (SCRUM-38).
    expect(canvas.getByText(/2 of 3 passed/)).toBeInTheDocument();
    expect(
      canvas.getByRole("button", { name: "Retry stage" }),
    ).toBeInTheDocument();
    const results = canvas.getByRole("link", { name: "See results" });
    expect(results.getAttribute("href")).toContain("/debrief");
    expect(canvasElement.querySelector("canvas")).not.toBeNull();
    expect(canvas.queryByRole("alert")).toBeNull();
  },
};
