import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";
import { XRFixtureStage } from "../components/XRFixtureStage";

const meta = {
  title: "XR/Fixture",
  component: XRFixtureStage,
} satisfies Meta<typeof XRFixtureStage>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Fixture loads: poster, live canvas, timings, caps, AR button (SCRUM-22). */
export const FixtureLoads: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(
      canvas.getByRole("img", { name: "Volcano poster" }),
    ).toBeInTheDocument();
    await canvas.findByText(/poster: \d+ms/, {}, { timeout: 15000 });
    await canvas.findByText(/first frame: \d+ms/, {}, { timeout: 20000 });
    const el = canvasElement.querySelector("canvas");
    expect(el).not.toBeNull();
    for (const row of ["webxr", "immersive-ar", "immersive-vr"]) {
      expect(canvas.getByText(row)).toBeInTheDocument();
    }
    const button = canvas.getByRole("button");
    expect(button).toBeDisabled();
    expect(canvas.queryByRole("alert")).toBeNull();
  },
};

/** Dragging the canvas orbits without errors (SCRUM-22). */
export const OrbitDrag: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/first frame: \d+ms/, {}, { timeout: 20000 });
    const el = canvasElement.querySelector("canvas");
    expect(el).not.toBeNull();
    if (el === null) {
      return;
    }
    const rect = el.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    await userEvent.pointer([
      { target: el, coords: { x: cx, y: cy }, keys: "[MouseLeft>]" },
      { coords: { x: cx + 120, y: cy - 40 } },
      { keys: "[/MouseLeft]" },
    ]);
    expect(canvasElement.querySelector("canvas")).not.toBeNull();
    expect(canvas.queryByRole("alert")).toBeNull();
  },
};
