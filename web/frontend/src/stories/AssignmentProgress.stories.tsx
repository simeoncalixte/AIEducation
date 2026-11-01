import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { api } from "../api";
import { AppRoutes } from "../App";
import { SessionProvider } from "../session";
import { ensureLoggedOut, loginAs, logout } from "./helpers";

let testNavigate: ((path: string) => void) | null = null;

/**
 * Story-only navigator: progress ids come from the live assign API,
 * so stories resolve them after logging in, then reach the detail
 * view through this handle.
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
  title: "Pages/AssignmentProgress",
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
 * Progress detail: attempts, rating, and flags (SCRUM-185). The
 * seeded live lesson pins no challenges, so no verdicts exist to
 * override here; verdict override stays covered by the API suite
 * (test_override_reflects_in_progress_same_session).
 */
export const ProgressRoundTrip: Story = {
  args: { route: "/assignments" },
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
    await api.rateAttempt(attempt_id, 4);
    await logout(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/assignments/${id}`);
    await canvas.findByRole("heading", { name: /Volcanoes.*Room 1/ });
    const main = within(canvas.getByRole("main"));
    expect(
      main.getByRole("link", { name: "Assignments" }),
    ).toBeInTheDocument();
    expect(main.getByRole("heading", { name: "Sam" })).toBeInTheDocument();
    expect(
      main.getByText("Enjoyment rating:", { exact: false }),
    ).toBeInTheDocument();
    expect(main.getByText("4")).toBeInTheDocument();
    expect(main.getByText(/1 attempt\(s\)/)).toBeInTheDocument();
    expect(
      main.getByRole("heading", { name: /Attempt #\d+/ }),
    ).toBeInTheDocument();
    expect(
      main.getByText("in progress", { exact: false }),
    ).toBeInTheDocument();
    expect(
      main.getByText("No verdicts yet for this attempt."),
    ).toBeInTheDocument();

    // Flag the attempt with a general note; the flag renders inline.
    await userEvent.type(
      main.getByLabelText("Note"),
      "Storybook flag note.",
    );
    await userEvent.click(
      main.getByRole("button", { name: "Flag misconception" }),
    );
    await main.findByText("Flag recorded.");
    expect(
      main.getByText("Storybook flag note.", { exact: false }),
    ).toBeInTheDocument();
    expect(main.queryByText("No flags on this attempt.")).toBeNull();
    await logout(canvas);
  },
};

/** An unknown assignment id renders the 404 page (SCRUM-185). */
export const UnknownAssignment404: Story = {
  args: { route: "/assignments" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    expect(testNavigate).not.toBeNull();
    testNavigate?.("/assignments/9999");
    await canvas.findByText("Something went wrong");
    const main = within(canvas.getByRole("main"));
    expect(
      main.getByText("Unknown assignment", { exact: false }),
    ).toBeInTheDocument();
    await logout(canvas);
  },
};

/** Logged-out visits land on the login form (SCRUM-185). */
export const LoggedOutRedirects: Story = {
  args: { route: "/assignments/1" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await canvas.findByLabelText("Login name");
  },
};
