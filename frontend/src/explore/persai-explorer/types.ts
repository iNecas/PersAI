export interface ChatMessage {
  role: "user" | "agent" | "system" | "tool";
  content: string;
  createdAt: number;
  toolCall?: ToolCall;
}

export interface ToolCall {
  role: "user" | "tool" | "system" | "assistant";
  result: string | null;
  callId: string;
  toolName: string;
  args: Record<string, string>;
}
