import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  createMockClient,
  createStreamResponse,
  streamChunks,
} from "./test-utils";
import { PersaiExplorer } from "./PersaiExplorer";
import { Client } from "./api";
import { useVariableDefinitionAndState } from "@perses-dev/dashboards";

// Mock the Client constructor
jest.mock("./api", () => ({
  Client: jest.fn(),
}));

// Mock the prometheus plugin
jest.mock("@perses-dev/prometheus-plugin", () => ({
  DEFAULT_PROM: {
    kind: "PrometheusDatasource",
    name: "default",
  },
  PROM_DATASOURCE_KIND: "PrometheusDatasource",
}));

// Mock plugin system components that might cause issues
jest.mock("@perses-dev/plugin-system", () => ({
  DatasourceSelect: ({ onChange, value, label }: any) => (
    <select
      data-testid="datasource-select"
      aria-label={label}
      value={value?.name || "default"}
      onChange={(e) =>
        onChange({ name: e.target.value, kind: "PrometheusDatasource" })
      }
    >
      <option value="default">Default Prometheus</option>
      <option value="thanos-auth">thanos-auth</option>
    </select>
  ),
  useListDatasourceSelectItems: () => ({ data: [] }),
  datasourceSelectValueToSelector: (value: any) => value,
  DataQueriesProvider: ({ children }: any) => <div>{children}</div>,
  TimeRangeProvider: ({ children }: any) => <div>{children}</div>,
  TimeRangeControls: () => <div data-testid="time-range-controls" />,
  useSuggestedStepMs: () => 30000,
  DatasourceStoreContext: React.createContext({
    listDatasourceSelectItems: jest.fn(),
    getDatasource: jest.fn(),
    getDatasourceClient: jest.fn().mockResolvedValue({
      options: {
        datasourceUrl: "/proxy/globaldatasources/prometheus",
      },
    }),
  }),
}));

// Mock Panel component that shows the chart
jest.mock("@perses-dev/dashboards", () => ({
  Panel: () => <div data-testid="prometheus-chart" />,
  useVariableDefinitionAndState: jest.fn(),
}));

describe("PersaiExplorer", () => {
  let mockClient: jest.Mocked<Client>;

  beforeEach(() => {
    mockClient = createMockClient();
    (Client as jest.Mock).mockImplementation(() => mockClient);

    // Mock the persai_url global variable hook
    (useVariableDefinitionAndState as jest.Mock).mockReturnValue({
      state: { value: "http://localhost:8000" },
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe("Complete Conversation Flow", () => {
    it("should handle a full user interaction from question to AI response", async () => {
      // Arrange: Set up streaming response
      const streamResponse = createStreamResponse([
        streamChunks.turnStart(),
        streamChunks.textProgress("Based on my analysis"),
        streamChunks.textProgress(", the CPU usage is "),
        streamChunks.textProgress("currently at 45%."),
        streamChunks.turnComplete(
          "Based on my analysis, the CPU usage is currently at 45%.",
        ),
      ]);

      mockClient.turnCreate.mockResolvedValue(streamResponse);

      // Act: Render and interact
      render(<PersaiExplorer />);

      // Clear default text and type new question
      const input = screen.getByPlaceholderText("Enter your query here");
      userEvent.clear(input);
      userEvent.type(input, "What is the current CPU usage?");

      const submitButton = screen.getByRole("button", { name: "Submit Query" });
      userEvent.click(submitButton);

      // Assert: Verify the full flow
      // 1. User message should appear
      await waitFor(() => {
        expect(
          screen.getByText("What is the current CPU usage?"),
        ).toBeInTheDocument();
      });

      // 2. Session should be created
      expect(mockClient.sessionCreate).toHaveBeenCalledTimes(1);

      // 3. AI response should stream in
      await waitFor(() => {
        expect(
          screen.getByText(
            /Based on my analysis, the CPU usage is currently at 45%/,
          ),
        ).toBeInTheDocument();
      });

      // 4. Button should be re-enabled after streaming
      await waitFor(() => {
        expect(submitButton).toBeEnabled();
        expect(submitButton).toHaveTextContent("Submit Query");
      });

      // 5. Input should be cleared
      expect(input).toHaveValue("");
    });

    it("should handle multiple messages in the same session", async () => {
      // First message
      const firstResponse = createStreamResponse([
        streamChunks.turnStart(),
        streamChunks.turnComplete("The current time is 2:30 PM."),
      ]);

      mockClient.turnCreate.mockResolvedValueOnce(firstResponse);

      render(<PersaiExplorer />);

      const input = screen.getByPlaceholderText("Enter your query here");
      userEvent.clear(input);
      userEvent.type(input, "What time is it?");
      userEvent.click(screen.getByRole("button", { name: "Submit Query" }));

      await waitFor(() => {
        expect(
          screen.getByText("The current time is 2:30 PM."),
        ).toBeInTheDocument();
      });

      // Second message - should reuse session
      const secondResponse = createStreamResponse([
        streamChunks.turnStart(),
        streamChunks.turnComplete("The weather is sunny and 72°F."),
      ]);

      mockClient.turnCreate.mockResolvedValueOnce(secondResponse);

      userEvent.type(input, "What is the weather?");
      userEvent.click(screen.getByRole("button", { name: "Submit Query" }));

      await waitFor(() => {
        expect(screen.getByText("What is the weather?")).toBeInTheDocument();
        expect(
          screen.getByText("The weather is sunny and 72°F."),
        ).toBeInTheDocument();
      });

      // Should create session only once
      expect(mockClient.sessionCreate).toHaveBeenCalledTimes(1);
      expect(mockClient.turnCreate).toHaveBeenCalledTimes(2);
    });
  });

  describe("Tool Execution Flow", () => {
    it("should display Prometheus query results with chart", async () => {
      const streamResponse = createStreamResponse([
        streamChunks.turnStart(),
        streamChunks.textProgress("Let me check the CPU usage for you."),
        streamChunks.toolExecution(
          "execute_range_query",
          {
            query: "rate(cpu_usage_seconds_total[5m])",
            start: "2024-01-01T00:00:00Z",
            end: "2024-01-01T01:00:00Z",
          },
          JSON.stringify({
            status: "success",
            data: {
              resultType: "matrix",
              result: [
                {
                  metric: { instance: "server1" },
                  values: [[1704067200, "0.45"]],
                },
              ],
            },
          }),
        ),
        streamChunks.turnComplete(
          "Let me check the CPU usage for you. The query shows CPU usage is at 45%.",
        ),
      ]);

      mockClient.turnCreate.mockResolvedValue(streamResponse);

      render(<PersaiExplorer />);

      const input = screen.getByPlaceholderText("Enter your query here");
      userEvent.clear(input);
      userEvent.type(input, "Show CPU usage metrics");
      userEvent.click(screen.getByRole("button", { name: "Submit Query" }));

      // Wait for tool execution
      await waitFor(() => {
        // Should show the query in the TextField
        const queryField = screen.getByDisplayValue(
          "rate(cpu_usage_seconds_total[5m])",
        );
        expect(queryField).toBeInTheDocument();
      });

      // Should render the chart component
      expect(screen.getByTestId("prometheus-chart")).toBeInTheDocument();
    });
  });

  describe("Error Handling", () => {
    let consoleLogSpy: jest.SpyInstance;

    beforeEach(() => {
      // Silence console.log for error handling tests
      consoleLogSpy = jest.spyOn(console, "error").mockImplementation();
    });

    afterEach(() => {
      // Restore console.log after each test
      consoleLogSpy.mockRestore();
    });

    it("should handle and display API errors gracefully", async () => {
      mockClient.sessionCreate.mockRejectedValueOnce(
        new Error("Network error"),
      );

      render(<PersaiExplorer />);

      const input = screen.getByPlaceholderText("Enter your query here");
      userEvent.clear(input);
      userEvent.type(input, "Test query");
      userEvent.click(screen.getByRole("button", { name: "Submit Query" }));

      // Should show error alert
      await waitFor(() => {
        expect(screen.getByRole("alert")).toHaveTextContent("Network error");
      });

      // Should be able to dismiss error
      const closeButton = screen.getByTitle("Close");
      userEvent.click(closeButton);

      await waitFor(() => {
        expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      });

      // Should be able to retry
      mockClient.sessionCreate.mockResolvedValueOnce({
        session_id: "new-session",
      });
      mockClient.turnCreate.mockResolvedValueOnce(
        createStreamResponse([
          streamChunks.turnStart(),
          streamChunks.turnComplete("Success!"),
        ]),
      );

      userEvent.click(screen.getByRole("button", { name: "Submit Query" }));

      await waitFor(() => {
        expect(screen.getByText("Success!")).toBeInTheDocument();
      });
    });

    it("should handle streaming errors", async () => {
      const errorStream = {
        [Symbol.asyncIterator]: () => ({
          next: async () => {
            throw new Error("Stream interrupted");
          },
        }),
      };

      mockClient.turnCreate.mockResolvedValueOnce(errorStream);

      render(<PersaiExplorer />);

      const input = screen.getByPlaceholderText("Enter your query here");
      userEvent.clear(input);
      userEvent.type(input, "Test query");
      userEvent.click(screen.getByRole("button", { name: "Submit Query" }));

      await waitFor(() => {
        expect(screen.getByRole("alert")).toHaveTextContent(
          "Stream interrupted",
        );
      });
    });
  });

  describe("User Interactions", () => {
    it("should submit on Ctrl+Enter", async () => {
      const streamResponse = createStreamResponse([
        streamChunks.turnStart(),
        streamChunks.turnComplete("Response to keyboard shortcut"),
      ]);

      mockClient.turnCreate.mockResolvedValue(streamResponse);

      render(<PersaiExplorer />);

      const input = screen.getByPlaceholderText("Enter your query here");
      userEvent.clear(input);
      userEvent.type(input, "Test with keyboard");

      // Simulate Ctrl+Enter
      userEvent.keyboard("{Control>}{Enter}{/Control}");

      await waitFor(() => {
        expect(screen.getByText("Test with keyboard")).toBeInTheDocument();
        expect(
          screen.getByText("Response to keyboard shortcut"),
        ).toBeInTheDocument();
      });
    });

    it("should show streaming state in UI", async () => {
      let resolveStream: () => void;
      const streamPromise = new Promise<void>((resolve) => {
        resolveStream = resolve;
      });

      const slowStream = {
        [Symbol.asyncIterator]: () => ({
          next: async () => {
            await streamPromise;
            return { done: true };
          },
        }),
      };

      mockClient.turnCreate.mockResolvedValue(slowStream);

      render(<PersaiExplorer />);

      const input = screen.getByPlaceholderText("Enter your query here");
      userEvent.clear(input);
      userEvent.type(input, "Slow query");

      const submitButton = screen.getByRole("button", { name: "Submit Query" });
      userEvent.click(submitButton);

      // Should show streaming state
      await waitFor(() => {
        expect(submitButton).toBeDisabled();
        expect(submitButton).toHaveTextContent("Streaming...");
      });

      // Should show loading indicator
      expect(screen.getByRole("progressbar")).toBeInTheDocument();

      // Complete the stream
      resolveStream!();

      await waitFor(() => {
        expect(submitButton).toBeEnabled();
        expect(submitButton).toHaveTextContent("Submit Query");
        expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
      });
    });
  });
});
