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
 * reach the brief composer through this handle.
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
  title: "Pages/BriefComposer",
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

/** Composer shows fields beside directives; submit lands on the draft dossier (SCRUM-181). */
export const SubmitRoundTrip: Story = {
  args: { route: "/lessons" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    const id = await volcanoesId();
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/lessons/${id}/brief`);
    await canvas.findByRole("heading", { name: "Brief: Volcanoes" });
    const form = within(canvas.getByRole("main"));
    expect(
      form.getByText("Cover the three eruption stages in order."),
    ).toBeInTheDocument();
    for (const label of [
      "Objectives (one per line)",
      "Mental models (one per line)",
      "Focus",
      "Must-include (comma-separated)",
      "Must-avoid (comma-separated)",
      "Priority",
      "Scope",
    ]) {
      expect(form.getByLabelText(label)).toBeInTheDocument();
    }
    expect(form.getByLabelText("Priority")).toHaveValue("1");
    await userEvent.type(
      form.getByLabelText("Objectives (one per line)"),
      "sci.eruptions",
    );
    await userEvent.type(
      form.getByLabelText("Mental models (one per line)"),
      "Magma rises through a vent.",
    );
    await userEvent.type(
      form.getByLabelText("Focus"),
      "Storybook chamber-to-surface drill.",
    );
    await userEvent.type(
      form.getByLabelText("Must-include (comma-separated)"),
      "crater diagram",
    );
    await userEvent.click(
      form.getByRole("button", { name: "Submit brief" }),
    );
    await canvas.findByRole("heading", { name: /Volcanoes · v\d+/ });
    const dossier = within(canvas.getByRole("main"));
    await dossier.findByText("Brief recorded.");
    expect(
      dossier.getAllByText("Storybook chamber-to-surface drill.", {
        exact: false,
      }).length,
    ).toBeGreaterThan(0);
    expect(
      dossier.getByRole("heading", { name: "Directive coverage" }),
    ).toBeInTheDocument();
    await logout(canvas);
  },
};

/** Blank focus is rejected with an error and stays on the composer (SCRUM-181). */
export const BlankFocusRejected: Story = {
  args: { route: "/lessons" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    const id = await volcanoesId();
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/lessons/${id}/brief`);
    await canvas.findByRole("heading", { name: "Brief: Volcanoes" });
    const form = within(canvas.getByRole("main"));
    await userEvent.click(
      form.getByRole("button", { name: "Submit brief" }),
    );
    await form.findByText("Brief rejected (invalid_brief)", {
      exact: false,
    });
    expect(
      form.getByRole("heading", { name: "Brief: Volcanoes" }),
    ).toBeInTheDocument();
    await logout(canvas);
  },
};

/** An unknown lesson id renders the 404 page (SCRUM-181). */
export const UnknownLesson404: Story = {
  args: { route: "/lessons" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    expect(testNavigate).not.toBeNull();
    testNavigate?.("/lessons/9999/brief");
    await canvas.findByText("Unknown lesson", { exact: false });
    await logout(canvas);
  },
};

/** Logged-out visits land on the login form (SCRUM-181). */
export const LoggedOutRedirects: Story = {
  args: { route: "/lessons/1/brief" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await canvas.findByLabelText("Login name");
  },
};
