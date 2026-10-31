import type { StorybookConfig } from "@storybook/react-vite";

const apiTarget = process.env.API_URL ?? "http://127.0.0.1:5001";

const config: StorybookConfig = {
  stories: ["../src/**/*.stories.@(ts|tsx)"],
  addons: [
    "@storybook/addon-essentials",
    "@storybook/addon-interactions",
  ],
  framework: { name: "@storybook/react-vite", options: {} },
  viteFinal: async (config) => {
    // Live-server interaction tests go through the same /api proxy as
    // the dev server: real backend, seeded database, no mocks.
    config.server = {
      ...config.server,
      proxy: {
        "/api": { target: apiTarget, changeOrigin: true },
      },
    };
    return config;
  },
};

export default config;
