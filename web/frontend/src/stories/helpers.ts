/**
 * Helpers for live-server interaction stories (SCRUM-192).
 *
 * Every helper drives the real UI against the live API (no mocks).
 * Stories normalize the shared server database and browser session
 * first so each play is order-independent, and log out at the end to
 * leave a clean state.
 */
import { expect, userEvent, waitFor, within } from "@storybook/test";
import { ApiError, api } from "../api";

export type Canvas = ReturnType<typeof within>;

/**
 * Restore seeded demo data on the live server.
 *
 * Stories share one server database for the whole run; without this,
 * mutating stories (directives, briefs, edits, approvals) leak state
 * into later ones. Requires ALLOW_TEST_RESET=1 on the server, which
 * test-live.sh sets.
 */
export async function resetServer(): Promise<void> {
  try {
    await api.testReset();
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      throw new Error(
        "Live-server reset unavailable: start the API with " +
          "ALLOW_TEST_RESET=1 (test-live.sh and review.sh do this).",
      );
    }
    throw err;
  }
}

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

/** Reset server data, then log out through the UI when in. */
export async function ensureLoggedOut(canvas: Canvas): Promise<void> {
  await resetServer();
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
