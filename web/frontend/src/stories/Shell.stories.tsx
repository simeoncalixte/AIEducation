import type { Meta, StoryObj } from "@storybook/react";
import { expect, within } from "@storybook/test";
import { MemoryRouter } from "react-router-dom";
import type { User } from "../api";
import { Shell } from "../components/Shell";

const tess: User = { id: 1, name: "Tess", role: "teacher" };
const ash: User = { id: 2, name: "Ash", role: "admin" };
const sam: User = { id: 3, name: "Sam", role: "student" };

const meta = {
  title: "Shell/Layout",
  component: Shell,
  decorators: [
    (Story) => (
      <MemoryRouter>
        <Story />
      </MemoryRouter>
    ),
  ],
  args: { user: null, flash: null, children: <p>Page body</p> },
} satisfies Meta<typeof Shell>;

export default meta;
type Story = StoryObj<typeof meta>;

export const LoggedOut: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(
      canvas.getByRole("link", { name: "Log in" }),
    ).toBeInTheDocument();
    expect(
      canvas.queryByRole("link", { name: "Log out" }),
    ).toBeNull();
    expect(
      canvas.queryByRole("link", { name: "Review" }),
    ).toBeNull();
  },
};

export const Teacher: Story = {
  args: { user: tess },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    for (const name of ["Review", "Lessons", "Assign"]) {
      expect(canvas.getByRole("link", { name })).toBeInTheDocument();
    }
    expect(canvas.queryByRole("link", { name: "Audit" })).toBeNull();
    expect(canvas.getByText("Tess (teacher)")).toBeInTheDocument();
    expect(
      canvas.getByRole("link", { name: "Log out" }),
    ).toBeInTheDocument();
  },
};

export const Admin: Story = {
  args: { user: ash },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(canvas.getByRole("link", { name: "Audit" })).toBeInTheDocument();
    expect(canvas.getByText("Ash (admin)")).toBeInTheDocument();
  },
};

export const Student: Story = {
  args: { user: sam },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(canvas.getByRole("link", { name: "Home" })).toBeInTheDocument();
    expect(
      canvas.queryByRole("link", { name: "Review" }),
    ).toBeNull();
    expect(canvas.getByText("Sam (student)")).toBeInTheDocument();
  },
};

export const WithFlash: Story = {
  args: { user: tess, flash: "Logged in as Tess (teacher)." },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(
      canvas.getByText("Logged in as Tess (teacher)."),
    ).toBeInTheDocument();
  },
};
