import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { api } from "../api";
import { AppRoutes } from "../App";
import { SessionProvider } from "../session";
import { ensureLoggedOut, loginAs, logout } from "./helpers";

let testNavigate: ((path: string) => void) | null = null;

/**
 * Story-only navigator: edit ids come from the seeded queues, so
 * stories resolve them through the live API after logging in, then
 * reach the edit form through this handle.
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
  title: "Pages/EditDraft",
  component: LiveApp,
} satisfies Meta<typeof LiveApp>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Resolve a seeded queue row id through the live API. */
async function queueId(
  kind: "asset" | "stage" | "lesson",
  match: (row: {
    title: string;
    status: string;
    low_impact: boolean;
    version_no: number;
  }) => boolean,
): Promise<number> {
  const { queues } = await api.review();
  const row = queues[kind].find(match);
  expect(row).toBeDefined();
  return row?.id ?? 0;
}

/** Asset edit prefills rationale + content_ref; save renders on the dossier (SCRUM-179). */
export const AssetEditRoundTrip: Story = {
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
    const current = (await api.dossier("asset", id)).dossier;
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/review/asset/${id}/edit`);
    await canvas.findByRole("heading", { name: /Edit draft: Volcano Model/ });
    const edit = within(canvas.getByRole("main"));
    expect(edit.getByLabelText("Rationale")).toHaveValue(current.rationale);
    const contentRef = edit.getByLabelText("Content ref");
    expect(contentRef).toHaveValue(current.content_ref ?? "");
    await userEvent.clear(edit.getByLabelText("Rationale"));
    await userEvent.type(
      edit.getByLabelText("Rationale"),
      "Storybook edit note.",
    );
    await userEvent.clear(contentRef);
    await userEvent.type(contentRef, "content/volcano-storybook.glb");
    await userEvent.click(edit.getByRole("button", { name: "Save draft" }));
    await canvas.findByRole("heading", { name: /Volcano Model \(prop\) · v2/ });
    const back = within(canvas.getByRole("main"));
    await back.findByText("Edit recorded.");
    expect(
      back.getAllByText("Storybook edit note.", { exact: false }).length,
    ).toBeGreaterThan(0);
    expect(
      back.getAllByText("content/volcano-storybook.glb", { exact: false })
        .length,
    ).toBeGreaterThan(0);
    await logout(canvas);
  },
};

/** Lesson edit has no content_ref; save renders on the dossier (SCRUM-179). */
export const LessonEditRoundTrip: Story = {
  args: { route: "/review" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    const id = await queueId(
      "lesson",
      (row) =>
        row.title.includes("Volcanoes") &&
        row.status === "draft" &&
        // Other stories may draft further lesson versions (SCRUM-181);
        // the seeded v3 draft keeps this edit deterministic.
        row.version_no === 3,
    );
    const current = (await api.dossier("lesson", id)).dossier;
    expect(testNavigate).not.toBeNull();
    testNavigate?.(`/review/lesson/${id}/edit`);
    await canvas.findByRole("heading", { name: /Edit draft: Volcanoes/ });
    const edit = within(canvas.getByRole("main"));
    expect(edit.getByLabelText("Rationale")).toHaveValue(current.rationale);
    expect(edit.queryByLabelText("Content ref")).toBeNull();
    await userEvent.clear(edit.getByLabelText("Rationale"));
    await userEvent.type(
      edit.getByLabelText("Rationale"),
      "Storybook pacing note.",
    );
    await userEvent.click(edit.getByRole("button", { name: "Save draft" }));
    await canvas.findByRole("heading", { name: /Volcanoes .* v3/ });
    const back = within(canvas.getByRole("main"));
    await back.findByText("Edit recorded.");
    expect(
      back.getAllByText("Storybook pacing note.", { exact: false }).length,
    ).toBeGreaterThan(0);
    await logout(canvas);
  },
};

/** Saving a non-draft surfaces the draft-only guard error (SCRUM-179). */
export const NonDraftGuarded: Story = {
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
    testNavigate?.(`/review/lesson/${id}/edit`);
    await canvas.findByRole("heading", { name: /Edit draft: Volcanoes/ });
    const edit = within(canvas.getByRole("main"));
    await userEvent.click(edit.getByRole("button", { name: "Save draft" }));
    await edit.findByText("Edit rejected (not_draft)", { exact: false });
    expect(
      edit.getByRole("heading", { name: /Edit draft: Volcanoes/ }),
    ).toBeInTheDocument();
    await logout(canvas);
  },
};

/** Logged-out visits land on the login form (SCRUM-179). */
export const LoggedOutRedirects: Story = {
  args: { route: "/review/asset/1/edit" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await canvas.findByLabelText("Login name");
  },
};
