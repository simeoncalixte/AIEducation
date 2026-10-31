import type { Meta, StoryObj } from "@storybook/react";
import { expect, within } from "@storybook/test";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes } from "../App";
import { SessionProvider } from "../session";
import { ensureLoggedOut, loginAs, logout } from "./helpers";

/** Full app at one route, driving the live server (no mocks). */
function LiveApp({ route }: { route: string }) {
  return (
    <MemoryRouter initialEntries={[route]}>
      <SessionProvider>
        <AppRoutes />
      </SessionProvider>
    </MemoryRouter>
  );
}

const meta = {
  title: "Pages/Home",
  component: LiveApp,
} satisfies Meta<typeof LiveApp>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Teacher home against the live server (SCRUM-176). */
export const TeacherHome: Story = {
  args: { route: "/home" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    const main = within(canvas.getByRole("main"));
    for (const name of ["Review queues", "Lessons", "Assignments"]) {
      expect(main.getByRole("link", { name })).toBeInTheDocument();
    }
    expect(main.queryByRole("link", { name: "Audit" })).toBeNull();
    await logout(canvas);
  },
};

/** Admin home shows the audit link (SCRUM-176). */
export const AdminHome: Story = {
  args: { route: "/home" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "ash");
    await canvas.findByText("Welcome, Ash");
    const main = within(canvas.getByRole("main"));
    expect(main.getByRole("link", { name: "Audit" })).toBeInTheDocument();
    await logout(canvas);
  },
};

/** Student home against the live server (SCRUM-176). */
export const StudentHome: Story = {
  args: { route: "/home" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "sam");
    await canvas.findByText("My assignments");
    const empty = canvas.queryByText(/No assignments yet\./);
    const table = canvas.queryByRole("table");
    expect(empty === null).not.toBe(table === null);
    if (table !== null) {
      const openLinks = within(table).getAllByRole("link", {
        name: "Open…",
      });
      expect(openLinks.length).toBeGreaterThan(0);
    }
    await logout(canvas);
  },
};
