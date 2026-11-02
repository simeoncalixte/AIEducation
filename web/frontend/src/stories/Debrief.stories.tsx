import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { api } from "../api";
import { AppRoutes } from "../App";
import { SessionProvider } from "../session";
import { ensureLoggedOut, loginAs, logout } from "./helpers";

let testNavigate: ((path: string) => void) | null = null;

/**
 * Story-only navigator: attempt ids come from the seeded school, so
 * stories resolve them through the live API after logging in, then
 * reach the debrief through this handle.
 */
function NavCapture() {
  testNavigate = useNavigate();
  return null;
}

/** Full app at one route, driving the live server (no mocks). */
function LiveApp({ route }: { route: string }) {
  return (
    <MemoryRouter initialEntries={[route]}>
      <SessionProvider>
        <NavCapture />
        <AppRoutes />
      </SessionProvider>
    </MemoryRouter>
  );
}

const meta = {
  title: "Pages/Debrief",
  component: LiveApp,
} satisfies Meta<typeof LiveApp>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Assign seeded Volcanoes to Room 1 through the live API (idempotent). */
async function volcanoesAssignmentId(): Promise<number> {
  const { options } = await api.assignments();
  const lesson = options.lessons.find((row) => row.title === "Volcanoes");
  const room = options.classrooms.find((row) =>
    row.name.includes("Room 1"),
  );
  expect(lesson).toBeDefined();
  expect(room).toBeDefined();
  const result = await api.assign({
    lesson_id: String(lesson?.id ?? 0),
    classroom_id: String(room?.id ?? 0),
    student_id: "",
  });
  return result.assignment_id;
}

/**
 * Fresh attempts render the results page with no verdicts yet
 * (SCRUM-188). The seeded live lesson pins no challenges, so a new
 * attempt lands straight on the debrief.
 */
export const EmptyDebrief: Story = {
  args: { route: "/home" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    const id = await volcanoesAssignmentId();
    await logout(canvas);
    await loginAs(canvas, "sam");
    await canvas.findByText("My assignments");
    const { attempt_id } = await api.startAttempt(id);
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/play/attempt/${attempt_id}/debrief`);
    await canvas.findByText("Goal verdicts");
    const main = within(canvas.getByRole("main"));
    expect(main.getByText("No verdicts yet.")).toBeInTheDocument();
    expect(
      main.getByRole("button", { name: "Save rating" }),
    ).toBeInTheDocument();
    expect(
      main.getByRole("button", { name: "Retry lesson" }),
    ).toBeInTheDocument();
    await logout(canvas);
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
 * Answering in the scene issues verdicts on the debrief (SCRUM-23).
 * Telemetry round-trip made visible: the answer posts events, the
 * evaluator issues goal verdicts, the results page renders them.
 */
export const AnsweredRoundTrip: Story = {
  args: { route: "/home" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
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
    const id = await volcanoesAssignmentId();
    await logout(canvas);
    await loginAs(canvas, "sam");
    await canvas.findByText("My assignments");
    const { attempt_id } = await api.startAttempt(id);
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/play/attempt/${attempt_id}/challenge/1`);
    await canvas.findByText("Challenge 1 of 1");
    const challenge = within(canvas.getByRole("main"));
    await userEvent.click(challenge.getByRole("checkbox", { name: "crater" }));
    await userEvent.type(
      challenge.getByLabelText("Note (optional)"),
      "Spike answer.",
    );
    await userEvent.click(
      challenge.getByRole("button", { name: "See results" }),
    );
    await canvas.findByText("Goal verdicts");
    const main = within(canvas.getByRole("main"));
    const craterRow = main.getByText("crater").closest("tr");
    expect(craterRow).not.toBeNull();
    expect(
      within(craterRow as HTMLElement).getByText("pass"),
    ).toBeInTheDocument();
    const ventRow = main.getByText("vent").closest("tr");
    expect(ventRow).not.toBeNull();
    expect(
      within(ventRow as HTMLElement).getByText("fail"),
    ).toBeInTheDocument();
    await logout(canvas);
  },
};

/** Unknown attempts render the 404 page (SCRUM-188). */
export const UnknownAttempt: Story = {
  args: { route: "/home" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "sam");
    await canvas.findByText("My assignments");
    expect(testNavigate).not.toBeNull();
    testNavigate?.("/play/attempt/999999/debrief");
    await canvas.findByText("Something went wrong");
    const main = within(canvas.getByRole("main"));
    expect(
      main.getByText("Unknown attempt", { exact: false }),
    ).toBeInTheDocument();
    await logout(canvas);
  },
};

/** Logged-out visits land on the login form (SCRUM-188). */
export const LoggedOutRedirects: Story = {
  args: { route: "/play/attempt/1/debrief" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await canvas.findByLabelText("Login name");
  },
};
