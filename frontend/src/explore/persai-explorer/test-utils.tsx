import type { Client } from "./api";
import type { AgentTurnResponseStreamChunk } from "llama-stack-client/resources/agents/turn";

// Create a mock client factory
export function createMockClient() {
  const mockClient = {
    sessionCreate: jest.fn(),
    sessionDelete: jest.fn(),
    turnCreate: jest.fn(),
  } as unknown as jest.Mocked<Client>;

  // Set up default successful responses
  mockClient.sessionCreate.mockResolvedValue({
    session_id: "test-session-123",
  });

  return mockClient;
}

// Helper to create streaming responses
export function createStreamResponse(
  chunks: Array<Partial<AgentTurnResponseStreamChunk>>,
) {
  let index = 0;

  return {
    [Symbol.asyncIterator]: () => ({
      next: async () => {
        if (index < chunks.length) {
          const chunk = chunks[index++];
          return { value: chunk, done: false };
        }
        return { done: true };
      },
    }),
  };
}

// Helper to create common stream chunks
export const streamChunks = {
  turnStart: (): Partial<AgentTurnResponseStreamChunk> => ({
    event: {
      payload: {
        event_type: "turn_start" as const,
      },
    },
  }),

  textProgress: (text: string): Partial<AgentTurnResponseStreamChunk> => ({
    event: {
      payload: {
        event_type: "step_progress" as const,
        delta: {
          type: "text",
          text: text,
        },
      },
    },
  }),

  toolExecution: (
    toolName: string,
    args: Record<string, any>,
    result: string,
  ): Partial<AgentTurnResponseStreamChunk> => ({
    event: {
      payload: {
        event_type: "step_complete" as const,
        step_details: {
          step_type: "tool_execution" as const,
          tool_calls: [
            {
              tool_name: toolName,
              arguments: args,
            },
          ],
          tool_responses: [
            {
              tool_name: toolName,
              content: result,
            },
          ],
        },
      },
    },
  }),

  turnComplete: (message: string): Partial<AgentTurnResponseStreamChunk> => ({
    event: {
      payload: {
        event_type: "turn_complete" as const,
        turn: {
          output_message: {
            content: message,
          },
        },
      },
    },
  }),
};
