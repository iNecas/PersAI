import { ReactElement, memo } from "react";
import { Box } from "@mui/material";
import { DatasourceSelector } from "@perses-dev/core";

import { ChatMessage } from "../types";
import { ToolCall } from "./ToolCall";

import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

interface MessageProps {
  message: ChatMessage;
  datasource: DatasourceSelector;
}

const Message = memo(({ message, datasource }: MessageProps): ReactElement => {
  if (message.role === "user") {
    return (
      <Box display="flex" justifyContent="flex-end">
        <Box
          bgcolor="primary.dark"
          color="white"
          px={1.5}
          borderRadius={2}
          maxWidth="500px"
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeRaw, rehypeSanitize]}
          >
            {message.content}
          </ReactMarkdown>
        </Box>
      </Box>
    );
  }

  if (message.role === "tool") {
    return <ToolCall toolCall={message.toolCall} datasource={datasource} />;
  }

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw, rehypeSanitize]}
    >
      {message.content}
    </ReactMarkdown>
  );
});

interface MessagesProps {
  messages: ChatMessage[];
  datasource: DatasourceSelector;
}

const Messages = memo(
  ({ messages, datasource }: MessagesProps): ReactElement => {
    return (
      <>
        {messages.map((m, index) => (
          <Message
            key={`${m.createdAt}-${index}`}
            message={m}
            datasource={datasource}
          />
        ))}
      </>
    );
  },
);

export default Messages;
