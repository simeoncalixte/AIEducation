import type { Meta, StoryObj } from "@storybook/react";
import { expect, within } from "@storybook/test";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { api } from "../api";
import { AppRoutes } from "../App";
import { SessionProvider } from "../session";
import { ensureLoggedOut, loginAs, logout } from "./helpers";

let testNavigate: ((path: string) => void) | null = null;

/**
 * Story-only navigator: attempt ids come from the seeded school, so
 * stories resolve them through the live API after logging in, then
 * reach the challenge through this handle.
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
  title: "Pages/Challenge",
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
 * Bad challenge indexes render the 404 page (SCRUM-187). The seeded
 * live lesson pins no challenges, so any index is out of range.
 */
export const BadIndex: Story = {
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
    testNavigate?.(`/play/attempt/${attempt_id}/challenge/9`);
    await canvas.findByText("Something went wrong");
    const main = within(canvas.getByRole("main"));
    expect(
      main.getByText("Unknown challenge", { exact: false }),
    ).toBeInTheDocument();
    await logout(canvas);
  },
};

/** Unknown attempts render the 404 page (SCRUM-187). */
export const UnknownAttempt: Story = {
  args: { route: "/home" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "sam");
    await canvas.findByText("My assignments");
    expect(testNavigate).not.toBeNull();
    testNavigate?.("/play/attempt/999999/challenge/1");
    await canvas.findByText("Something went wrong");
    const main = within(canvas.getByRole("main"));
    expect(
      main.getByText("Unknown attempt", { exact: false }),
    ).toBeInTheDocument();
    await logout(canvas);
  },
};

/** Logged-out visits land on the login form (SCRUM-187). */
export const LoggedOutRedirects: Story = {
  args: { route: "/play/attempt/1/challenge/1" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await canvas.findByLabelText("Login name");
  },
};
