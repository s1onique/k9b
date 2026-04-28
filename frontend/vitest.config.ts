import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/vitest.setup.ts",
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    testTimeout: 30000,
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      reportsDirectory: "../coverage/frontend",
      exclude: [
        "node_modules",
        "dist",
        ".vite",
        "vitest.config.ts",
        "src/vitest.setup.ts",
        "src/main.tsx",
        "**/*.test.ts",
        "**/*.test.tsx",
        "**/*.spec.ts",
        "**/*.spec.tsx",
        "src/types.ts",
        "src/theme.ts",
        "src/themes.css",
        "src/index.css",
      ],
    },
  },
});