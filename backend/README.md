# PersAI Backend

A FastAPI backend service that provides a REST API for interacting with an AI agent. The service enables conversational AI interactions with specialized tools for querying Prometheus metrics through Perses proxy.

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

### Installation

```bash
# Install dependencies
uv sync

# Configure the model of your choice (more configuration options below)
export OPENAI_API_KEY="******"
export PERSAI_DEFAULT_MODEL="gpt-4o-mini"

# Start the server
uv run uvicorn main:app
```

### Development mode

```bash
# For development mode with auto-reload
uv run uvicorn main:app --reload
```

The server will start on `http://localhost:8000` by default.

Tor run on different port, run

``` bash
uv run uvicorn main:app --port 9090
```

## Configuration

Configure LLM providers by setting the appropriate API keys:

- **OpenAI**: `OPENAI_API_KEY` (models: gpt-4o-mini, gpt-4o)
- **Google Gemini**: `GOOGLE_API_KEY` (models: gemini-1.5-flash, gemini-1.5-pro)
- **Anthropic**: `ANTHROPIC_API_KEY` (models: claude-3-5-haiku, claude-3-5-sonnet)

Additional optional configuration options:

- `PERSAI_DEFAULT_MODEL` - Override default model selection
   If not provided, the first model with provided API KEY (based on ordering above)
   is used.
- `PERSAI_SYSTEM_PROMPT` - Override the LLM system prompt
- `PERSES_API_URL` - Base URL for Perses API (e.g., `http://perses.example.com`)
   If not provided, it uses the request headers and uses the origin of the request.
- `LOG_LEVEL` - Logging level (default: INFO)

## Development

See [the docs directory](./docs) to learn more details about the project
structure, conventions, testing etc.

## License

See [LICENSE](LICENSE) file for details.
