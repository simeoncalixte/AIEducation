import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { api } from "../api";
import { AppRoutes } from "../App";
import { SessionProvider } from "../session";
import { ensureLoggedOut, loginAs, logout } from "./helpers";

let testNavigate: ((path: string) => void) | null = null;

/**
 * Story-only navigator: lesson ids come from the seeded list, so
 * stories resolve them through the live API after logging in, then
 * reach the directives panel through this handle.
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
  title: "Pages/Directives",
  component: LiveApp,
} satisfies Meta<typeof LiveApp>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Resolve the seeded Volcanoes lesson id through the live API. */
async function volcanoesId(): Promise<number> {
  const { lessons } = await api.lessons();
  const row = lessons.find((lesson) => lesson.title === "Volcanoes");
  expect(row).toBeDefined();
  return row?.id ?? 0;
}

/** Panel lists directives with scope labels and roster-backed scope picker (SCRUM-182). */
export const PanelRoundTrip: Story = {
  args: { route: "/lessons" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    const id = await volcanoesId();
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/lessons/${id}/directives`);
    await canvas.findByRole("heading", { name: "Directives: Volcanoes" });
    const main = within(canvas.getByRole("main"));
    expect(
      main.getByText("Cover the three eruption stages in order."),
    ).toBeInTheDocument();
    expect(main.getByText("Class-wide")).toBeInTheDocument();
    expect(
      main.getAllByRole("button", { name: "Deactivate" }).length,
    ).toBeGreaterThan(0);
    expect(
      main.getAllByRole("link", { name: "Edit…" }).length,
    ).toBeGreaterThan(0);
    for (const label of [
      "Focus",
      "Scope",
      "Must-include (comma-separated)",
      "Must-avoid (comma-separated)",
      "Priority",
    ]) {
      expect(main.getByLabelText(label)).toBeInTheDocument();
    }
    expect(main.getByLabelText("Priority")).toHaveValue("1");
    expect(
      main.getByRole("option", { name: "Class-wide" }),
    ).toBeInTheDocument();
    expect(main.getByRole("option", { name: "Sam" })).toBeInTheDocument();

    // Class-wide steer.
    await userEvent.type(
      main.getByLabelText("Focus"),
      "Storybook class-wide steer.",
    );
    await userEvent.click(
      main.getByRole("button", { name: "Record directive" }),
    );
    await main.findByText("Directive recorded.");
    const wideRow = main
      .getByText("Storybook class-wide steer.")
      .closest("tr");
    expect(wideRow).not.toBeNull();
    expect(within(wideRow as HTMLElement).getByText("Class-wide"))
      .toBeInTheDocument();

    // Per-student steer scoped to Sam.
    const scope = main.getByLabelText("Scope");
    const sam = main.getByRole("option", { name: "Sam" });
    await userEvent.selectOptions(scope, [sam as HTMLOptionElement]);
    await userEvent.type(
      main.getByLabelText("Focus"),
      "Storybook scoped steer.",
    );
    await userEvent.click(
      main.getByRole("button", { name: "Record directive" }),
    );
    await main.findByText("Directive recorded.");
    const scopedRow = main.getByText("Storybook scoped steer.").closest("tr");
    expect(scopedRow).not.toBeNull();
    expect(within(scopedRow as HTMLElement).getByText("Sam"))
      .toBeInTheDocument();

    // Deactivate the steer just created; the row stays, flagged off.
    await userEvent.click(
      within(scopedRow as HTMLElement).getByRole("button", {
        name: "Deactivate",
      }),
    );
    await main.findByText("Directive deactivated.");
    const retired = main.getByText("Storybook scoped steer.").closest("tr");
    expect(within(retired as HTMLElement).getByText("no")).toBeInTheDocument();
    await logout(canvas);
  },
};

/** Blank focus is rejected with an error and stays on the panel (SCRUM-182). */
export const BlankFocusRejected: Story = {
  args: { route: "/lessons" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    const id = await volcanoesId();
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/lessons/${id}/directives`);
    await canvas.findByRole("heading", { name: "Directives: Volcanoes" });
    const main = within(canvas.getByRole("main"));
    await userEvent.click(
      main.getByRole("button", { name: "Record directive" }),
    );
    await main.findByText("Directive rejected (invalid_directive)", {
      exact: false,
    });
    expect(
      main.getByRole("heading", { name: "Directives: Volcanoes" }),
    ).toBeInTheDocument();
    await logout(canvas);
  },
};

/** An unknown lesson id renders the 404 page (SCRUM-182). */
export const UnknownLesson404: Story = {
  args: { route: "/lessons" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    expect(testNavigate).not.toBeNull();
    testNavigate?.("/lessons/9999/directives");
    await canvas.findByText("Unknown lesson", { exact: false });
    await logout(canvas);
  },
};

/** Logged-out visits land on the login form (SCRUM-182). */
export const LoggedOutRedirects: Story = {
  args: { route: "/lessons/1/directives" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await canvas.findByLabelText("Login name");
  },
};
