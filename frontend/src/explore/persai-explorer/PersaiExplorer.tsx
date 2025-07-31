import {
  Box,
  Button,
  Stack,
  TextField,
  CircularProgress,
  Alert,
} from "@mui/material";
import { ChatMessage } from "./types";
import Messages from "./components/Messages";
import {
  DatasourceSelect,
  DatasourceSelectValue,
  datasourceSelectValueToSelector,
  useListDatasourceSelectItems,
  DatasourceStoreContext,
} from "@perses-dev/plugin-system";
import { useVariableDefinitionAndState } from "@perses-dev/dashboards";
import { DatasourceSelector } from "@perses-dev/core";
import {
  DEFAULT_PROM,
  PROM_DATASOURCE_KIND,
} from "@perses-dev/prometheus-plugin";
import { ReactElement, useState, useContext, KeyboardEvent } from "react";
import { Client } from "./api";
import { ToolCall as LlamaToolCall } from "llama-stack-client/resources/shared";
import { ToolResponse as LlamaToolResponse } from "llama-stack-client/resources";
import { AgentTurnResponseStreamChunk } from "llama-stack-client/resources/agents/turn";
import { ToolExecutionStep } from "llama-stack-client/resources";

function updateChunk(
  prevMessages: ChatMessage[],
  { delta, full }: { delta?: string; full?: string },
): ChatMessage[] {
  let updatedMessages = [...prevMessages];

  const updateMessage = (current: string): string => {
    if (delta) return current + delta;
    return full!;
  };

  // Check if the last message exists and is an agent message
  const lastMessage = prevMessages[prevMessages.length - 1];
  if (lastMessage && lastMessage.role === "agent") {
    const updatedMessage: ChatMessage = {
      ...lastMessage,
      content: updateMessage(lastMessage.content),
    };
    updatedMessages[updatedMessages.length - 1] = updatedMessage;
    return updatedMessages;
  }

  // Otherwise, append a new message if content/response is significant
  const newMessage: ChatMessage = {
    role: "agent",
    content: updateMessage(""),
    createdAt: Math.floor(Date.now() / 1000),
  };

  return [...updatedMessages, newMessage];
}

function addToolResponse(
  prevMessages: ChatMessage[],
  toolCall: LlamaToolCall,
  toolResponse?: LlamaToolResponse,
): ChatMessage[] {
  const toolCallId = toolCall.call_id;
  const createdAt = Math.floor(Date.now() / 1000);
  const toolMessage: ChatMessage = {
    role: "tool",
    content: toolResponse?.content as string,
    createdAt: createdAt,
    toolCall: {
      role: "tool",
      callId: toolCallId,
      toolName: toolCall.tool_name,
      args: toolCall.arguments as Record<string, string>,
      result: toolResponse?.content as string,
    },
  };

  // Check if there's an existing message with matching tool_call_id
  const existingMessageIndex = prevMessages.findIndex(
    (msg) => msg.toolCall?.callId === toolCallId,
  );

  if (existingMessageIndex !== -1) {
    // Update existing tool message
    const updatedMessages = [...prevMessages];
    updatedMessages[existingMessageIndex] = toolMessage;
    return updatedMessages;
  } else {
    // Add new tool message
    return [...prevMessages, toolMessage];
  }
}

function addUserRequest(
  prevMessages: ChatMessage[],
  message: string,
): ChatMessage[] {
  return [
    ...prevMessages,
    {
      role: "user",
      content: message,
      createdAt: Math.floor(Date.now() / 1000),
    } as ChatMessage,
  ];
}

function updateMessagesFromChunk(
  prevMessages: ChatMessage[],
  chunk: AgentTurnResponseStreamChunk,
): ChatMessage[] {
  const payload = chunk.event.payload;

  switch (payload.event_type) {
    case "turn_start":
      return prevMessages;

    case "step_start":
      return prevMessages;

    case "step_progress":
      if (payload.delta.type === "text") {
        return updateChunk(prevMessages, { delta: payload.delta.text });
      }
      return prevMessages;

    case "step_complete":
      if (payload.step_details.step_type === "tool_execution") {
        const toolStep = payload.step_details as ToolExecutionStep;
        const newMessages = toolStep.tool_calls.reduce(
          (prevMessages, toolCall, index) => {
            const toolResponse = toolStep.tool_responses?.[index];
            return addToolResponse(prevMessages, toolCall, toolResponse);
          },
          prevMessages,
        );
        return newMessages;
      }
      return prevMessages;

    case "turn_complete":
      if (payload.turn.output_message) {
        return updateChunk(prevMessages, {
          full: payload.turn.output_message.content as string,
        });
      }
      return prevMessages;

    case "turn_awaiting_input":
      return prevMessages;

    default:
      return prevMessages;
  }
}

export function PersaiExplorer(): ReactElement {
  const [queryText, setQueryText] = useState<string>();
  const [sessionId, setSessionId] = useState<string>();
  const [messages, setMessages] = useState<Array<ChatMessage>>([]);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [datasource, setDatasource] =
    useState<DatasourceSelector>(DEFAULT_PROM);

  const persaiUrlVar = useVariableDefinitionAndState("persai_url", "global");

  const datastore = useContext(DatasourceStoreContext);

  const { data } = useListDatasourceSelectItems(PROM_DATASOURCE_KIND);

  function handleDatasourceChange(next: DatasourceSelectValue): void {
    const datasourceSelector = datasourceSelectValueToSelector(
      next,
      {},
      data,
    ) ?? { kind: PROM_DATASOURCE_KIND };
    setDatasource(datasourceSelector);
  }

  const handleSubmit = async () => {
    const persaiUrl = persaiUrlVar?.state?.value as string;
    if (!persaiUrl) {
      console.error("'persai_url' not found");
      setError(
        "Could not determine PersAI backend url ('persai_url' global variable is missing). " +
          "Was the plugin installed properly?",
      );
      return;
    }
    // Slight hack to invoke some perses api to refresh the auth token if necessary.
    datastore?.getDatasource(datasource.kind);

    const datasourceClient = await datastore!.getDatasourceClient(datasource);
    const datasourcePath = datasourceClient?.options?.datasourceUrl;
    if (!datasourcePath) {
      console.error("Could not load datasourcePath", datasourceClient);
      setError("Could not determine the datasource path");
      return;
    }

    setError(null);
    setMessages((prevMessages) => addUserRequest(prevMessages, queryText));
    const message = queryText;
    setQueryText("");
    setIsStreaming(true);

    try {
      const client = new Client(persaiUrl);

      let newSessionId = sessionId;

      if (!newSessionId) {
        const session = await client.sessionCreate();
        newSessionId = session.session_id;
        setSessionId(newSessionId);
      }

      const response = await client.turnCreate(
        newSessionId,
        datasourcePath,
        message,
      );

      for await (const chunk of response) {
        setMessages((prevMessages) =>
          updateMessagesFromChunk(prevMessages, chunk),
        );
      }
      setIsStreaming(false);
    } catch (error) {
      console.error("error", error);
      setError(
        error instanceof Error ? error.message : "An unexpected error occurred",
      );
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.ctrlKey && event.key === "Enter") {
      event.preventDefault();
      handleSubmit();
    }
  };

  return (
    <Stack gap={2} sx={{ width: "100%" }}>
      <Box sx={{ minWidth: 300 }}>
        <DatasourceSelect
          datasourcePluginKind={PROM_DATASOURCE_KIND}
          value={datasource}
          onChange={handleDatasourceChange}
          label="Prometheus Datasource"
        />
      </Box>
      {messages.length > 0 && (
        <Box
          sx={{
            border: "1px solid grey",
            padding: 2,
            minHeight: 100,
          }}
        >
          <Messages messages={messages} datasource={datasource} />
          {isStreaming && (
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 2 }}>
              <CircularProgress size={32} />
            </Box>
          )}
        </Box>
      )}
      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      <TextField
        multiline
        rows={4}
        variant="outlined"
        value={queryText}
        onChange={(e) => setQueryText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Enter your query here"
        fullWidth
        disabled={isStreaming}
        data-testid="query-textfield"
      />
      <Button variant="contained" onClick={handleSubmit} disabled={isStreaming}>
        {isStreaming ? "Streaming..." : "Submit Query"}
      </Button>
    </Stack>
  );
}
