import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";
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
  title: "Pages/Login",
  component: LiveApp,
} satisfies Meta<typeof LiveApp>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Login flow against the live server (SCRUM-175): pilot users list,
 * unknown-login error, login-by-name landing home, logout back out.
 */
export const LoginFlow: Story = {
  args: { route: "/login" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);

    await canvas.findByText("tess");
    for (const marker of ["ash", "sam", "teacher", "admin", "student"]) {
      expect(canvas.getAllByText(marker).length).toBeGreaterThan(0);
    }

    await loginAs(canvas, "nobody");
    await canvas.findByText(/Unknown login/);

    const useButtons = canvas.getAllByRole("button", { name: "Use" });
    await userEvent.click(useButtons[0]);
    await canvas.findByText("Welcome, Tess");
    expect(
      canvas.getByText("Logged in as Tess (teacher)."),
    ).toBeInTheDocument();
    expect(
      canvas.getByRole("link", { name: "Review queues" }),
    ).toBeInTheDocument();

    await logout(canvas);
    expect(canvas.getByText("Logged out.")).toBeInTheDocument();
  },
};
