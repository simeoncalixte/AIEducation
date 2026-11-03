import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { api } from "../api";
import { AppRoutes } from "../App";
import { SessionProvider } from "../session";
import { ensureLoggedOut, loginAs, logout } from "./helpers";

let testNavigate: ((path: string) => void) | null = null;

/**
 * Story-only navigator: dossier ids come from the seeded queues, so
 * stories resolve them through the live API after logging in, then
 * reach the dossier through this handle.
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
  title: "Pages/ReviewDossier",
  component: LiveApp,
} satisfies Meta<typeof LiveApp>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Resolve a seeded queue row id through the live API. */
async function queueId(
  kind: "asset" | "stage" | "lesson",
  match: (row: { title: string; status: string; low_impact: boolean }) => boolean,
): Promise<number> {
  const { queues } = await api.review();
  const row = queues[kind].find(match);
  expect(row).toBeDefined();
  return row?.id ?? 0;
}

/** Asset dossier against the live server (SCRUM-178). */
export const AssetDossier: Story = {
  args: { route: "/review" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    const id = await queueId(
      "asset",
      (row) => row.title.includes("Volcano Model") && row.status === "draft",
    );
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/review/asset/${id}`);
    await canvas.findByRole("heading", { name: /Volcano Model \(prop\) · v2/ });
    const main = within(canvas.getByRole("main"));
    for (const heading of [
      "Rationale",
      "What changed",
      "Directive coverage",
      "Previews",
      "Reuse matches",
      "Impact scores",
      "Used in",
      "Review actions",
      "Audit trail",
    ]) {
      expect(
        main.getByRole("heading", { name: new RegExp(heading) }),
      ).toBeInTheDocument();
    }
    for (const marker of [
      "vs v1",
      "content_ref",
      "Cover the three eruption",
      "Rock Samples",
      "0.72",
      "Volcanoes / Eruption",
      "centerpiece",
      "No previews rendered for this version yet.",
    ]) {
      expect(
        main.getByText(marker, { exact: false }),
      ).toBeInTheDocument();
    }
    await logout(canvas);
  },
};

/** Stage dossier against the live server (SCRUM-178). */
export const StageDossier: Story = {
  args: { route: "/review" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    const id = await queueId(
      "stage",
      (row) => row.title.includes("Eruption") && row.status === "draft",
    );
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/review/stage/${id}`);
    await canvas.findByRole("heading", { name: /Eruption · v2/ });
    const main = within(canvas.getByRole("main"));
    expect(
      main.getByRole("heading", { name: /Asset uses/ }),
    ).toBeInTheDocument();
    for (const marker of ["Volcano Model", "Label the Parts", "challenge"]) {
      expect(
        main.getAllByText(marker, { exact: false }).length,
      ).toBeGreaterThan(0);
    }
    for (const heading of ["Challenge goals", "Lesson context"]) {
      expect(
        main.getByRole("heading", { name: new RegExp(heading) }),
      ).toBeInTheDocument();
    }
    for (const marker of [
      "crater",
      "vent",
      "goal-attempted",
      "move magma",
      "class default",
      "Manager",
      "guide",
    ]) {
      expect(
        main.getAllByText(marker, { exact: false }).length,
      ).toBeGreaterThan(0);
    }
    await logout(canvas);
  },
};

/** Lesson dossier against the live server (SCRUM-178). */
export const LessonDossier: Story = {
  args: { route: "/review" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    const id = await queueId(
      "lesson",
      (row) => row.title.includes("Volcanoes") && row.status === "published",
    );
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/review/lesson/${id}`);
    await canvas.findByRole("heading", { name: /Volcanoes .* v2/ });
    const main = within(canvas.getByRole("main"));
    for (const heading of ["Stage composition", "Audit trail"]) {
      expect(
        main.getByRole("heading", { name: new RegExp(heading) }),
      ).toBeInTheDocument();
    }
    for (const marker of ["Eruption", "published", "Live."]) {
      expect(
        main.getAllByText(marker, { exact: false }).length,
      ).toBeGreaterThan(0);
    }
    await logout(canvas);
  },
};

/** Low-impact flag with evidence on the dossier (SCRUM-178). */
export const LowImpactDossier: Story = {
  args: { route: "/review" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    const id = await queueId("asset", (row) => row.low_impact);
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/review/asset/${id}`);
    await canvas.findByRole("heading", { name: /Sediment Tray/ });
    const main = within(canvas.getByRole("main"));
    for (const marker of ["Low impact", "0.31", "12", "Room 1", "0.09"]) {
      expect(
        main.getAllByText(marker, { exact: false }).length,
      ).toBeGreaterThan(0);
    }
    expect(
      main.getByRole("button", { name: "Revise" }),
    ).toBeInTheDocument();
    await logout(canvas);
  },
};

/** Approve + edit record rationales and update state (SCRUM-178). */
export const DossierActions: Story = {
  args: { route: "/review" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    const id = await queueId(
      "asset",
      (row) => row.title.includes("Volcano Model") && row.status === "draft",
    );
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/review/asset/${id}`);
    await canvas.findByRole("heading", { name: /Volcano Model \(prop\) · v2/ });
    const main = within(canvas.getByRole("main"));
    await userEvent.type(
      main.getByLabelText("Approve rationale"),
      "Storybook approval note.",
    );
    await userEvent.click(main.getByRole("button", { name: "Approve" }));
    await main.findByText("Approval recorded.");
    expect(
      main.getAllByText("Storybook approval note.", { exact: false }).length,
    ).toBeGreaterThan(0);
    expect(main.getAllByText("approved").length).toBeGreaterThan(0);
    await userEvent.click(main.getByRole("button", { name: "Edit draft" }));
    await canvas.findByRole("heading", { name: /Edit draft/ });
    const edit = within(canvas.getByRole("main"));
    const field = edit.getByLabelText("Rationale");
    await userEvent.clear(field);
    await userEvent.type(field, "Storybook polish note.");
    await userEvent.click(edit.getByRole("button", { name: "Save draft" }));
    await canvas.findByRole("heading", { name: /Volcano Model \(prop\) · v2/ });
    const back = within(canvas.getByRole("main"));
    await back.findByText("Edit recorded.");
    expect(
      back.getAllByText("Storybook polish note.", { exact: false }).length,
    ).toBeGreaterThan(0);
    await logout(canvas);
  },
};

/** Students see the staff-only error (SCRUM-178). */
export const StudentForbidden: Story = {
  args: { route: "/review" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    const id = await queueId(
      "asset",
      (row) => row.title.includes("Volcano Model") && row.status === "draft",
    );
    await logout(canvas);
    await loginAs(canvas, "sam");
    await canvas.findByText("My assignments");
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/review/asset/${id}`);
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

/** Logged-out visits land on the login form (SCRUM-178). */
export const LoggedOutRedirects: Story = {
  args: { route: "/review/asset/1" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await canvas.findByLabelText("Login name");
  },
};
