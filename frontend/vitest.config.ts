import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    // Keep isolated worker threads: verified against src/test/isolation with maxWorkers=1.
    pool: "threads",
    isolate: true,
    maxWorkers: 4,
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
