import type { Config } from "@jest/types";

// Since jest.shared doesn't exist, we'll create a complete config
const jestConfig: Config.InitialOptions = {
  preset: "ts-jest",
  testEnvironment: "jsdom",

  setupFilesAfterEnv: ["<rootDir>/src/setup-tests.ts"],

  testMatch: ["**/*.test.ts", "**/*.test.tsx"],

  collectCoverageFrom: [
    "src/**/*.{ts,tsx}",
    "!src/**/*.d.ts",
    "!src/**/index.ts",
    "!src/setup-tests.ts",
    "!src/bootstrap.tsx",
    "!src/index-federation.ts",
  ],

  moduleFileExtensions: ["ts", "tsx", "js", "jsx", "json"],

  testPathIgnorePatterns: ["/node_modules/", "/dist/"],
};

export default jestConfig;
