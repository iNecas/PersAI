# Backend implementation overview

## Project Structure

```
persai/
├── server/                    # HTTP server code
│   ├── server.py              # FastAPI application factory
│   ├── endpoints.py           # FastAPI route handlers
│   ├── auth.py                # JWT authentication logic
│   └── token_validator.py     # JWT token validation
│ 
├── agent/                     # LLM agent code
│   ├── config.py              # Dynamic provider configuration
│   ├── agent.py               # Agent integration via llamastack
│   └── tools.py               # Agent tools implementation (prometheus)
│ 
├── errors/                    # Exceptions related code
│   ├── exceptions.py          # Custom exception classes
│   └── exception_handlers.py  # HTTP exception mapping
│ 
├── logging.py                 # Logging configuration
└── version.py                 # Version information

tests/
├── unit/
│   ├── agent/                 # Tests for agent-related components
│   └── server/                # Tests for server-related components
└── integration/               # API integration tests
```

## __init__.py Files Convention

The project is composed of multiple sub-packages. To better differentiate between an external interface
and an internal structure of the packages, all imports used outside of the package should be exported
explicitly in `__init__.py` file of the sub-package.

## Dependency management

The project uses [https://docs.astral.sh/uv/] to deal with dependencies.

## Implementation details

### Authentication

The backend service assumes to be used from the Perses UI and uses the cookie
providing JWT tokens for the authorization:

- at the beginning of the request, it verified validity of the token by trying
  to use the refresh token to issue a new token: if it succeeds, the token is
  trusted (cached for an hour before re-validation).

- the tokens are also used in during the tool calls to authenticate against
  Perses data-source proxy again as the same user.
  
When running Perses with `enable_auth: false`, you can disable the auth logic with

```bash
export PERSAI_AUTH=false
```
                           

### AI Agent Framework

We're currently using [Llama Stack](https://github.com/meta-llama/llama-stack)
for heavy-lifting of the LLM integration and basic agent implementation.

Given how active the field of agentic frameworks currently is, we try to limit
the amount of features used from the framework, and we're open to experiement
with different implementations if necessary.

### Tool calls implementation

Tool calls are currently implemented as client-provided python functions.
While we experimented with MCP at the beginning, we've found no added value
to justify the additional complexity. Given the tight coupling of the tools
with the rest of the project, treating the tool implementation as part
of the code-based provides better flexibility.
