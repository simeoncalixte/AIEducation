import type { Meta, StoryObj } from "@storybook/react";
import { expect, fireEvent, userEvent, waitFor, within } from "@storybook/test";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { AppRoutes } from "../App";
import { SessionProvider } from "../session";
import { ensureLoggedOut, loginAs, logout } from "./helpers";

let testNavigate: ((path: string) => void) | null = null;

/** Story-only navigator: reach /audit after logging in through the UI. */
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
  title: "Pages/Audit",
  component: LiveApp,
} satisfies Meta<typeof LiveApp>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Log in as the seeded admin and open the audit view. */
async function openAuditAs(canvas: ReturnType<typeof within>, name: string) {
  await ensureLoggedOut(canvas);
  await loginAs(canvas, name);
  await canvas.findByText(`Welcome, ${name === "ash" ? "Ash" : "Tess"}`);
  expect(testNavigate).not.toBeNull();
  testNavigate?.("/audit");
  await canvas.findByRole("heading", { name: "School audit" });
  return within(canvas.getByRole("main"));
}

/** Status tables plus the approval/publish trail (SCRUM-189). */
export const StatusAndTrail: Story = {
  args: { route: "/login" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const main = await openAuditAs(canvas, "ash");
    for (const marker of [
      "Room 1",
      "Volcanoes",
      "Drafts",
      "Published",
      "Tess",
      "approved",
      "published",
      "asset Volcano Model v1",
    ]) {
      expect(
        main.getAllByText(marker, { exact: false }).length,
      ).toBeGreaterThan(0);
    }
    await logout(canvas);
  },
};

/** Actor filter narrows the trail; students have no history (SCRUM-189). */
export const ActorFilter: Story = {
  args: { route: "/login" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const main = await openAuditAs(canvas, "ash");
    const actor = main.getByLabelText("Actor");
    const filter = main.getByRole("button", { name: "Filter" });

    const sam = main.getByRole("option", { name: "Sam (student)" });
    await userEvent.selectOptions(actor, [sam as HTMLOptionElement]);
    await userEvent.click(filter);
    await main.findByText("No history matches these filters.");

    const tess = main.getByRole("option", { name: "Tess (teacher)" });
    await userEvent.selectOptions(actor, [tess as HTMLOptionElement]);
    await userEvent.click(filter);
    await waitFor(() => {
      expect(
        main.queryByText("No history matches these filters."),
      ).toBeNull();
    });
    expect(main.getAllByText("approved").length).toBeGreaterThan(0);
    await logout(canvas);
  },
};

/** Date filters bound the trail; far bounds are deterministic (SCRUM-189). */
export const DateFilter: Story = {
  args: { route: "/login" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const main = await openAuditAs(canvas, "ash");
    const since = main.getByLabelText("Since");
    const filter = main.getByRole("button", { name: "Filter" });

    fireEvent.change(since, { target: { value: "2100-01-01" } });
    await userEvent.click(filter);
    await main.findByText("No history matches these filters.");

    fireEvent.change(since, { target: { value: "2000-01-01" } });
    await userEvent.click(filter);
    await waitFor(() => {
      expect(
        main.queryByText("No history matches these filters."),
      ).toBeNull();
    });
    expect(main.getAllByText("approved").length).toBeGreaterThan(0);
    await logout(canvas);
  },
};

/** Non-admin staff get the 403 page (SCRUM-189). */
export const TeacherForbidden: Story = {
  args: { route: "/login" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await openAuditAs(canvas, "tess");
    await canvas.findByText("school admins", { exact: false });
    await logout(canvas);
  },
};

/** Logged-out visits land on the login form (SCRUM-189). */
export const LoggedOutRedirects: Story = {
  args: { route: "/audit" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await canvas.findByLabelText("Login name");
  },
};
