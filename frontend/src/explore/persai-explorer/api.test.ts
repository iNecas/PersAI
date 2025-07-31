import { Client } from "./api";

describe("Client", () => {
  let client: Client;

  beforeEach(() => {
    // Reset environment variables
    delete process.env.REACT_APP_PERSAI_BACKEND_URL;
    client = new Client("http://localhost:8000");
  });

  describe("Constructor", () => {
    it("should create client with provided URL", () => {
      expect(client).toBeDefined();
    });

    it("should accept custom URL", () => {
      const customClient = new Client("http://custom-backend:8080");
      expect(customClient).toBeDefined();
    });

    it("should save the URL in the baseURL property", () => {
      const testURL = "http://test-backend:3000";
      const testClient = new Client(testURL);
      expect(testClient.baseURL).toBe(testURL);
    });
  });

  it("should call post for sessionCreate", () => {
    const mockPost = jest.fn().mockResolvedValue({ session_id: "test" });
    (client as any).post = mockPost;

    client.sessionCreate();

    expect(mockPost).toHaveBeenCalledWith("/session");
  });

  it("should call delete for sessionDelete", () => {
    const mockDelete = jest.fn().mockResolvedValue(undefined);
    (client as any).delete = mockDelete;

    client.sessionDelete("test-session");

    expect(mockDelete).toHaveBeenCalledWith("/session/test-session");
  });

  it("should call post with stream for turnCreate", () => {
    const mockPost = jest.fn().mockResolvedValue({});
    (client as any).post = mockPost;

    client.turnCreate("test-session", "/proxy/globaldatasources/prometheus", "Hello");

    expect(mockPost).toHaveBeenCalledWith("/session/test-session/turn?datasource_path=%2Fproxy%2Fglobaldatasources%2Fprometheus", {
      body: { message: "Hello" },
      stream: true,
    });
  });
});
