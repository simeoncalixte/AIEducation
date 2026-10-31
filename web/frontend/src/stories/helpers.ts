/**
 * Helpers for live-server interaction stories (SCRUM-192).
 *
 * Every helper drives the real UI against the live API (no mocks).
 * Stories normalize the shared browser session first so each play is
 * order-independent, and log out at the end to leave a clean state.
 */
import { expect, userEvent, waitFor, within } from "@storybook/test";

export type Canvas = ReturnType<typeof within>;

/** Wait until the shell has settled on a logged-in or logged-out view. */
export async function settle(canvas: Canvas): Promise<"in" | "out"> {
  await waitFor(() => {
    const out = canvas.queryByRole("link", { name: "Log out" });
    const field = canvas.queryByLabelText("Login name");
    expect(out ?? field).toBeTruthy();
  });
  return canvas.queryByRole("link", { name: "Log out" }) !== null
    ? "in"
    : "out";
}

/** Log out through the UI when a session is present. */
export async function ensureLoggedOut(canvas: Canvas): Promise<void> {
  const state = await settle(canvas);
  if (state === "in") {
    const link = canvas.getByRole("link", { name: "Log out" });
    await userEvent.click(link);
    await canvas.findByLabelText("Login name");
  }
}

/** Fill the login form and submit through the UI. */
export async function loginAs(canvas: Canvas, name: string): Promise<void> {
  const field = await canvas.findByLabelText("Login name");
  await userEvent.clear(field);
  await userEvent.type(field, name);
  await userEvent.click(canvas.getByRole("button", { name: "Log in" }));
}

/** Click "Log out" and wait for the login form to return. */
export async function logout(canvas: Canvas): Promise<void> {
  await userEvent.click(canvas.getByRole("link", { name: "Log out" }));
  await canvas.findByLabelText("Login name");
}
