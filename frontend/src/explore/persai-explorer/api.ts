import { SessionCreateResponse } from "llama-stack-client/resources/agents/session";
import { AgentTurnResponseStreamChunk } from "llama-stack-client/resources/agents/turn";
import { APIPromise, APIClient, DefaultQuery } from "llama-stack-client/core";
import { Stream } from "llama-stack-client/streaming";

export class Client extends APIClient {
  constructor(baseURL: string) {
    super({
      baseURL: baseURL,
      timeout: 30000 /* 30 seconds */,
      httpAgent: undefined,
      maxRetries: 3,
      fetch: (url: RequestInfo | URL, init?: RequestInit) => {
        return fetch(url, {
          ...init,
          // To pass the auth cookies to the agent
          credentials: "include",
        });
      },
    });
  }

  protected override defaultQuery(): DefaultQuery | undefined {
    return undefined;
  }

  sessionCreate(): APIPromise<SessionCreateResponse> {
    return this.post(`/session`);
  }

  sessionDelete(sessionId: string): APIPromise<void> {
    return this.delete(`/session/${sessionId}`);
  }

  turnCreate(
    sessionId: string,
    datasourcePath: string,
    message: string,
  ): APIPromise<Stream<AgentTurnResponseStreamChunk>> {
    const params = new URLSearchParams({ datasource_path: datasourcePath });
    return this.post(`/session/${sessionId}/turn?${params}`, {
      body: {
        message: message,
      },
      stream: true,
    }) as APIPromise<Stream<AgentTurnResponseStreamChunk>>;
  }
}
