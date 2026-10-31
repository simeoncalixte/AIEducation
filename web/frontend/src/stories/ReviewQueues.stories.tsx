import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { AppRoutes } from "../App";
import { SessionProvider } from "../session";
import { ensureLoggedOut, loginAs, logout } from "./helpers";

let testNavigate: ((path: string) => void) | null = null;

/**
 * Story-only navigator: students have no UI link to staff routes,
 * so the forbidden story reaches /review through this handle after
 * logging in through the real form.
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
  title: "Pages/ReviewQueues",
  component: LiveApp,
} satisfies Meta<typeof LiveApp>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Teacher queues against the live server (SCRUM-177). */
export const TeacherQueues: Story = {
  args: { route: "/review" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    await userEvent.click(canvas.getByRole("link", { name: "Review" }));
    await canvas.findByRole("heading", { name: "Review queues" });
    const main = within(canvas.getByRole("main"));
    for (const heading of [
      "Asset proposals",
      "Stage proposals",
      "Lesson proposals",
    ]) {
      expect(
        main.getByRole("heading", { name: heading }),
      ).toBeInTheDocument();
    }
    for (const marker of ["Volcano Model", "Eruption", "Volcanoes"]) {
      expect(
        main.getAllByText(marker, { exact: false }).length,
      ).toBeGreaterThan(0);
    }
    expect(main.getAllByText("draft").length).toBeGreaterThan(0);
    expect(main.getAllByText("published").length).toBeGreaterThan(0);
    expect(main.getAllByText("Low impact").length).toBeGreaterThan(0);
    const openLinks = main.getAllByRole("link", { name: "Open" });
    expect(openLinks.length).toBeGreaterThan(0);
    for (const link of openLinks) {
      expect(link.getAttribute("href")).toMatch(
        /^\/review\/(asset|stage|lesson)\/\d+$/,
      );
    }
    await logout(canvas);
  },
};

/** Students see the staff-only error (SCRUM-177). */
export const StudentForbidden: Story = {
  args: { route: "/review" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "sam");
    await canvas.findByText("My assignments");
    expect(testNavigate).not.toBeNull();
    testNavigate?.("/review");
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

/** Logged-out visits land on the login form (SCRUM-177). */
export const LoggedOutRedirects: Story = {
  args: { route: "/review" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await canvas.findByLabelText("Login name");
  },
};
