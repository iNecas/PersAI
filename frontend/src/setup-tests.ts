import "@testing-library/jest-dom";
import React from "react";

// Suppress console errors about ReactDOM.render warnings
const originalError = console.error;
beforeAll(() => {
  console.error = (...args: any[]) => {
    if (
      typeof args[0] === "string" &&
      args[0].includes("Warning: ReactDOM.render")
    ) {
      return;
    }
    originalError.call(console, ...args);
  };
});

afterAll(() => {
  console.error = originalError;
});

// Global mocks for Web APIs required by llama-stack-client
global.fetch = jest.fn(() =>
  Promise.resolve({
    json: () => Promise.resolve({}),
    text: () => Promise.resolve(""),
    ok: true,
    status: 200,
    statusText: "OK",
  } as Response),
);
global.Request = jest.fn() as any;
global.Response = jest.fn() as any;
global.Headers = jest.fn() as any;

// Mock ResizeObserver for components that use it
global.ResizeObserver = jest.fn(() => ({
  observe: jest.fn(),
  unobserve: jest.fn(),
  disconnect: jest.fn(),
}));

// Mock react-markdown and its plugins (used in Messages component)
jest.mock("react-markdown", () => ({
  __esModule: true,
  default: ({ children }: { children: string }) => {
    const React = require("react");
    return React.createElement("div", { className: "markdown" }, children);
  },
}));
jest.mock("remark-gfm", () => () => {});
jest.mock("rehype-raw", () => () => {});
jest.mock("rehype-sanitize", () => () => {});

// Mock Perses dependencies that are used in PersaiExplorer
jest.mock("@perses-dev/plugin-system", () => ({
  useTimeRange: () => ({
    timeRange: {
      $__timeRange: {
        from: "now-1h",
        to: "now",
      },
    },
  }),
  TimeRangeProvider: ({ children }: any) =>
    React.createElement(
      "div",
      { "data-testid": "time-range-provider" },
      children,
    ),
  DataQueriesProvider: ({ children }: any) =>
    React.createElement(
      "div",
      { "data-testid": "data-queries-provider" },
      children,
    ),
  TimeRangeControls: () =>
    React.createElement(
      "div",
      { "data-testid": "time-range-controls" },
      "Time Range Controls",
    ),
  useSuggestedStepMs: () => 1000,
  usePlugin: () => ({
    getPlugin: () => ({
      Panel: ({ spec }: any) =>
        React.createElement(
          "div",
          { "data-testid": "prometheus-chart" },
          React.createElement(
            "div",
            null,
            `Query: ${spec.queries?.[0]?.query || "No query"}`,
          ),
          React.createElement(
            "div",
            null,
            "Chart visualization would appear here",
          ),
        ),
    }),
  }),
}));

// Mock Panel component from dashboards (used in ToolCall)
jest.mock("@perses-dev/dashboards", () => ({
  Panel: ({ definition }: any) =>
    React.createElement(
      "div",
      { "data-testid": "prometheus-chart" },
      React.createElement(
        "div",
        null,
        `Query: ${definition?.spec?.queries?.[0]?.query || "No query"}`,
      ),
      React.createElement("div", null, "Chart visualization would appear here"),
    ),
}));
