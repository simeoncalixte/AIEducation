import type { Meta, StoryObj } from "@storybook/react";
import { expect, within } from "@storybook/test";
import { PilotRunReport } from "../components/PilotRunReport";

const meta = {
  title: "XR/Pilot run",
  component: PilotRunReport,
} satisfies Meta<typeof PilotRunReport>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Recorded pilot-run evidence renders with targets and verdicts (SCRUM-25). */
export const RecordedRuns: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(canvas.getByText("Pixel 10 Pro")).toBeInTheDocument();
    expect(canvas.getByText(/58ms PASS/)).toBeInTheDocument();
    expect(canvas.getByText("138ms")).toBeInTheDocument();
    expect(canvas.getAllByText(/target p95 <5000ms PASS/)).toHaveLength(2);
    expect(canvas.getByText(/7\.25ms/)).toBeInTheDocument();
    expect(canvas.getByText(/pending/)).toBeInTheDocument();
  },
};
