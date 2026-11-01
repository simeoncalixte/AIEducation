import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { AppRoutes } from "../App";
import { SessionProvider } from "../session";
import { ensureLoggedOut, loginAs, logout } from "./helpers";

let testNavigate: ((path: string) => void) | null = null;

/**
 * Story-only navigator: the assign flow lands on the list, and the
 * progress links carry assignment ids, so stories reach the list
 * through this handle after logging in.
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
  title: "Pages/Assignments",
  component: LiveApp,
} satisfies Meta<typeof LiveApp>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Assign flow: empty state, classroom + student assigns, guards (SCRUM-184). */
export const AssignRoundTrip: Story = {
  args: { route: "/assignments" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "tess");
    await canvas.findByText("Welcome, Tess");
    expect(testNavigate).not.toBeNull();
    testNavigate?.("/assignments");
    await canvas.findByRole("heading", { name: "Assignments" });
    const main = within(canvas.getByRole("main"));
    expect(
      main.getByText("No assignments yet. Assign a lesson below."),
    ).toBeInTheDocument();
    for (const label of ["Lesson", "Classroom", "Student"]) {
      expect(main.getByLabelText(label)).toBeInTheDocument();
    }

    // Blank target is rejected and adds no rows.
    await userEvent.click(
      main.getByRole("button", { name: "Assign lesson" }),
    );
    await main.findByText(/invalid_scope/);
    expect(main.queryByRole("table")).toBeNull();

    // Classroom assign: row appears with a progress link.
    const classroom = main.getByLabelText("Classroom");
    const room = main.getByRole("option", { name: /Room 1/ });
    await userEvent.selectOptions(classroom, [room as HTMLOptionElement]);
    await userEvent.click(
      main.getByRole("button", { name: "Assign lesson" }),
    );
    await main.findByText("Assignment recorded.");
    const table = main.getByRole("table");
    const wideRow = within(table).getByText("Volcanoes").closest("tr");
    expect(wideRow).not.toBeNull();
    for (const marker of ["Room 1", "Tess"]) {
      expect(
        within(wideRow as HTMLElement).getByText(marker),
      ).toBeInTheDocument();
    }
    const progressLink = within(wideRow as HTMLElement).getByRole("link", {
      name: "Progress…",
    });
    expect(progressLink.getAttribute("href")).toMatch(
      /^\/assignments\/\d+$/,
    );

    // Per-student assign scoped to Sam.
    const student = main.getByLabelText("Student");
    const sam = main.getByRole("option", { name: "Sam" });
    await userEvent.selectOptions(student, [sam as HTMLOptionElement]);
    await userEvent.click(
      main.getByRole("button", { name: "Assign lesson" }),
    );
    await main.findByText("Assignment recorded.");
    const scopedRow = within(table).getByText("Sam").closest("tr");
    expect(scopedRow).not.toBeNull();
    expect(
      within(scopedRow as HTMLElement).getByText("Volcanoes"),
    ).toBeInTheDocument();

    // Both targets at once is rejected; the two rows stand.
    const roomAgain = main.getByRole("option", { name: /Room 1/ });
    const samAgain = main.getByRole("option", { name: "Sam" });
    await userEvent.selectOptions(classroom, [roomAgain as HTMLOptionElement]);
    await userEvent.selectOptions(student, [samAgain as HTMLOptionElement]);
    await userEvent.click(
      main.getByRole("button", { name: "Assign lesson" }),
    );
    await main.findByText(/invalid_scope/);
    expect(within(table).getAllByText("Volcanoes").length).toBe(2);
    await logout(canvas);
  },
};

/** Students get the 403 page on the assignments list (SCRUM-184). */
export const StudentForbidden: Story = {
  args: { route: "/assignments" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await loginAs(canvas, "sam");
    await canvas.findByText("Welcome, Sam");
    expect(testNavigate).not.toBeNull();
    testNavigate?.("/assignments");
    await canvas.findByText("Something went wrong");
    const main = within(canvas.getByRole("main"));
    expect(main.getByText("403")).toBeInTheDocument();
    await logout(canvas);
  },
};

/** Logged-out visits land on the login form (SCRUM-184). */
export const LoggedOutRedirects: Story = {
  args: { route: "/assignments" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await ensureLoggedOut(canvas);
    await canvas.findByLabelText("Login name");
  },
};
