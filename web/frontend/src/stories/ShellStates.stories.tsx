import type { Meta, StoryObj } from "@storybook/react";
import { expect, within } from "@storybook/test";
import { MemoryRouter } from "react-router-dom";
import { ErrorPage } from "../components/ErrorPage";

const errorMeta = {
  title: "Shell/Error page",
  component: ErrorPage,
  decorators: [
    (Story) => (
      <MemoryRouter>
        <Story />
      </MemoryRouter>
    ),
  ],
} satisfies Meta<typeof ErrorPage>;

export default errorMeta;
type ErrorStory = StoryObj<typeof errorMeta>;

export const NotFound: ErrorStory = {
  args: { code: 404, message: "This page does not exist." },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(canvas.getByText("404")).toBeInTheDocument();
    expect(
      canvas.getByText(/This page does not exist\./),
    ).toBeInTheDocument();
    expect(
      canvas.getByRole("link", { name: "Back to home" }),
    ).toBeInTheDocument();
  },
};

export const TeacherAreaForbidden: ErrorStory = {
  args: { code: 403, message: "This area is for teachers and admins." },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(
      canvas.getByText(/This area is for teachers and admins\./),
    ).toBeInTheDocument();
  },
};

export const AdminAreaForbidden: ErrorStory = {
  args: { code: 403, message: "This area is for school admins." },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(
      canvas.getByText(/This area is for school admins\./),
    ).toBeInTheDocument();
  },
};
