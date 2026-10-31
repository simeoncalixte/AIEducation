import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { api } from "../api";
import { AppRoutes } from "../App";
import { SessionProvider } from "../session";
import { ensureLoggedOut, loginAs, logout } from "./helpers";

let testNavigate: ((path: string) => void) | null = null;

/**
 * Story-only navigator: edit ids come from freshly created steers, so
 * stories resolve the lesson through the live API after logging in,
 * then reach the edit form through this handle.
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
  title: "Pages/EditDirective",
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

/**
 * Edit prefills the form; save returns to the panel showing the
 * updated values (SCRUM-183). The story edits a freshly created
 * steer so seeded rows stay untouched and reruns stay isolated.
 */
export const EditRoundTrip: Story = {
  args: { route: "/lessons" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    const lessonId = await volcanoesId();
    const marker = `Storybook edit-me ${Date.now()}.`;
    const created = await api.createDirective(lessonId, {
      focus: marker,
      must_include: "",
      must_avoid: "",
      priority: "1",
      student_id: "",
    });
    const id = created.directive_id ?? 0;
    expect(id).toBeGreaterThan(0);
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/directives/${id}/edit`);
    await canvas.findByRole("heading", { name: `Edit directive #${id}` });
    const edit = within(canvas.getByRole("main"));
    expect(edit.getByLabelText("Focus")).toHaveValue(marker);
    expect(edit.getByLabelText("Must-include (comma-separated)")).toHaveValue(
      "",
    );
    expect(edit.getByLabelText("Must-avoid (comma-separated)")).toHaveValue(
      "",
    );
    expect(edit.getByLabelText("Priority")).toHaveValue("1");
    const edited = `Storybook edited focus ${Date.now()}.`;
    await userEvent.clear(edit.getByLabelText("Focus"));
    await userEvent.type(edit.getByLabelText("Focus"), edited);
    await userEvent.type(
      edit.getByLabelText("Must-include (comma-separated)"),
      "crater diagram",
    );
    await userEvent.clear(edit.getByLabelText("Priority"));
    await userEvent.type(edit.getByLabelText("Priority"), "3");
    await userEvent.click(
      edit.getByRole("button", { name: "Save directive" }),
    );
    await canvas.findByRole("heading", { name: "Directives: Volcanoes" });
    const panel = within(canvas.getByRole("main"));
    await panel.findByText("Directive updated.");
    const row = panel.getByText(edited).closest("tr");
    expect(row).not.toBeNull();
    const cells = within(row as HTMLElement).getAllByRole("cell");
    expect(cells[4]).toHaveTextContent("3");
    const detail = (await api.directive(id)).directive;
    expect(detail.focus).toBe(edited);
    expect(detail.must_include).toBe("crater diagram");
    expect(detail.priority).toBe(3);
    await logout(canvas);
  },
};

/** Blank focus is rejected with an error and stays on the form (SCRUM-183). */
export const BlankFocusRejected: Story = {
  args: { route: "/lessons" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    const lessonId = await volcanoesId();
    const created = await api.createDirective(lessonId, {
      focus: `Storybook blank-edit ${Date.now()}.`,
      must_include: "",
      must_avoid: "",
      priority: "1",
      student_id: "",
    });
    const id = created.directive_id ?? 0;
    expect(id).toBeGreaterThan(0);
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/directives/${id}/edit`);
    await canvas.findByRole("heading", { name: `Edit directive #${id}` });
    const edit = within(canvas.getByRole("main"));
    await userEvent.clear(edit.getByLabelText("Focus"));
    await userEvent.click(
      edit.getByRole("button", { name: "Save directive" }),
    );
    await edit.findByText("Directive rejected (invalid_directive)", {
      exact: false,
    });
    expect(
      edit.getByRole("heading", { name: `Edit directive #${id}` }),
    ).toBeInTheDocument();
    await logout(canvas);
  },
};

/** An unknown directive id renders the 404 page (SCRUM-183). */
export const UnknownDirective404: Story = {
  args: { route: "/lessons" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    expect(testNavigate).not.toBeNull();
    testNavigate?.("/directives/9999/edit");
    await canvas.findByText("Unknown directive", { exact: false });
    await logout(canvas);
  },
};

/** Logged-out visits land on the login form (SCRUM-183). */
export const LoggedOutRedirects: Story = {
  args: { route: "/directives/1/edit" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await canvas.findByLabelText("Login name");
  },
};
