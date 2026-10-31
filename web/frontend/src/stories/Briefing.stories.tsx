import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { api } from "../api";
import { AppRoutes } from "../App";
import { SessionProvider } from "../session";
import { ensureLoggedOut, loginAs, logout } from "./helpers";

let testNavigate: ((path: string) => void) | null = null;

/**
 * Story-only navigator: assignment ids come from the seeded school, so
 * stories resolve them through the live API after logging in, then
 * reach the briefing through this handle.
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
  title: "Pages/Briefing",
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

/** Published briefing with start-then-continue flow (SCRUM-186). */
export const PublishedBriefing: Story = {
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
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/play/${id}`);
    await canvas.findByRole("heading", { name: "Volcanoes" });
    const main = within(canvas.getByRole("main"));
    for (const heading of [
      "Objectives",
      "Ideas you will build",
      "Stages (1)",
    ]) {
      expect(
        main.getByRole("heading", { name: heading }),
      ).toBeInTheDocument();
    }
    for (const marker of ["sci.eruptions", "Eruptions move magma"]) {
      expect(
        main.getByText(marker, { exact: false }),
      ).toBeInTheDocument();
    }
    expect(main.getByText("Eruption", { exact: true })).toBeInTheDocument();
    const start = main.getByRole("button", {
      name: /Start lesson|Continue lesson/,
    });
    await userEvent.click(start);
    // The seeded live lesson pins no challenges, so start lands on
    // the migrated debrief page (SCRUM-188).
    await canvas.findByRole("heading", { name: "Volcanoes — results" });
    testNavigate?.(`/play/${id}`);
    const resumed = within(canvas.getByRole("main"));
    await resumed.findByRole("button", { name: "Continue lesson" });
    await userEvent.click(
      resumed.getByRole("button", { name: "Continue lesson" }),
    );
    await canvas.findByRole("heading", { name: "Volcanoes — results" });
    await logout(canvas);
  },
};

/** Unknown assignments render the 404 page (SCRUM-186). */
export const UnknownAssignment: Story = {
  args: { route: "/home" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "sam");
    await canvas.findByText("My assignments");
    expect(testNavigate).not.toBeNull();
    testNavigate?.("/play/999999");
    await canvas.findByText("Something went wrong");
    const main = within(canvas.getByRole("main"));
    expect(
      main.getByText("Unknown assignment", { exact: false }),
    ).toBeInTheDocument();
    await logout(canvas);
  },
};

/** Logged-out visits land on the login form (SCRUM-186). */
export const LoggedOutRedirects: Story = {
  args: { route: "/play/1" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await canvas.findByLabelText("Login name");
  },
};
