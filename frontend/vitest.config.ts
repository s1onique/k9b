import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/vitest.setup.ts",
    unstubGlobals: true,
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      reportsDirectory: "../coverage/frontend",
      thresholds: {
        lines: 90,
        statements: 90,
      },
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