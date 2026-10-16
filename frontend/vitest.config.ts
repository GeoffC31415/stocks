import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    // Keep process isolation: Vitest 4.1.11 batches files into one VM context
    // when vmThreads is focused to one worker, even with isolate: true.
    pool: "forks",
    isolate: true,
    maxWorkers: 2,
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: true,
  },
});
