import type { TestRunnerConfig } from "@storybook/test-runner";

const config: TestRunnerConfig = {
  async preVisit(page) {
    // Live-server plays wait on a real backend; give them room.
    await page.setDefaultTimeout(15000);
  },
};

export default config;
