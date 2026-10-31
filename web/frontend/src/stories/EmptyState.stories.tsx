import type { Meta, StoryObj } from "@storybook/react";
import { expect, within } from "@storybook/test";
import { EmptyState } from "../components/EmptyState";

const meta = {
  title: "Shell/Empty state",
  component: EmptyState,
} satisfies Meta<typeof EmptyState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const NoAssignments: Story = {
  args: {
    children: (
      <>No assignments yet. Your teacher&apos;s assignments will appear here.</>
    ),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(canvas.getByText(/No assignments yet\./)).toBeInTheDocument();
  },
};
