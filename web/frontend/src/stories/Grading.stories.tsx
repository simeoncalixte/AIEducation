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
 * reach the grading view through this handle.
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
  title: "Pages/Grading",
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

/** Publish the challenge lesson so attempts pin Label the Parts. */
async function publishChallengeLesson(): Promise<void> {
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
}

/**
 * Grading an open explanation end to end (SCRUM-129). The student
 * answers with an explanation note, the teacher sees the recorded
 * evidence beside the rubric criteria, records a grade, and the
 * teacher verdict appears on the results page.
 */
export const GradeExplanation: Story = {
  args: { route: "/home" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    await publishChallengeLesson();
    const id = await volcanoesAssignmentId();
    await logout(canvas);
    await loginAs(canvas, "sam");
    await canvas.findByText("My assignments");
    const { attempt_id } = await api.startAttempt(id);
    await api.answerChallenge(attempt_id, 1, {
      goals: ["explain"],
      note: "Magma rises through the vent.",
    });
    await logout(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/attempts/${attempt_id}/grading`);
    await canvas.findByText("Recorded evidence");
    const main = within(canvas.getByRole("main"));
    expect(
      main.getByText("Magma rises through the vent."),
    ).toBeInTheDocument();
    expect(
      main.getByText("Names magma as the moving material."),
    ).toBeInTheDocument();
    expect(main.getByText("Not graded yet.")).toBeInTheDocument();
    await userEvent.type(
      main.getByLabelText("Rationale for explain"),
      "Names magma.",
    );
    await userEvent.click(
      main.getByRole("button", { name: "Record grade" }),
    );
    await main.findByText("Evaluation recorded.");
    expect(await main.findByText("pass")).toBeInTheDocument();
    testNavigate?.(`/play/attempt/${attempt_id}/debrief`);
    await canvas.findByText("Goal verdicts");
    const results = within(canvas.getByRole("main"));
    const explainRow = results.getByText("explain").closest("tr");
    expect(explainRow).not.toBeNull();
    expect(
      within(explainRow as HTMLElement).getByText("(teacher graded)"),
    ).toBeInTheDocument();
    await logout(canvas);
  },
};

/** Students cannot open the grading view (SCRUM-129). */
export const StudentForbidden: Story = {
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
    testNavigate?.(`/attempts/${attempt_id}/grading`);
    await canvas.findByText("Something went wrong");
    const main = within(canvas.getByRole("main"));
    expect(
      main.getByText("This area is for teachers and admins.", {
        exact: false,
      }),
    ).toBeInTheDocument();
    await logout(canvas);
  },
};

/** Unknown attempts render the 404 page (SCRUM-129). */
export const UnknownAttempt: Story = {
  args: { route: "/home" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    expect(testNavigate).not.toBeNull();
    testNavigate?.("/attempts/999999/grading");
    await canvas.findByText("Something went wrong");
    const main = within(canvas.getByRole("main"));
    expect(
      main.getByText("Unknown attempt", { exact: false }),
    ).toBeInTheDocument();
    await logout(canvas);
  },
};
