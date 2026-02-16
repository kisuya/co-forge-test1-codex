import path from "node:path";

import { defineConfig } from "vitest/config";

const webNodeModules = path.resolve(__dirname, "./node_modules");

export default defineConfig({
  esbuild: {
    jsx: "automatic",
    jsxImportSource: "react",
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["../../tests/web/**/*.test.ts", "../../tests/web/**/*.test.tsx", "../../tests/web/test_*.tsx"],
    globals: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      react: path.resolve(webNodeModules, "react"),
      "react-dom": path.resolve(webNodeModules, "react-dom"),
      "@testing-library/react": path.resolve(webNodeModules, "@testing-library/react"),
      "@testing-library/jest-dom/vitest": path.resolve(
        webNodeModules,
        "@testing-library/jest-dom/vitest",
      ),
    },
  },
  server: {
    fs: {
      allow: [path.resolve(__dirname, "../..")],
    },
  },
});
