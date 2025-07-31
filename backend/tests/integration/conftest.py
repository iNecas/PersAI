import asyncio
import pytest
import pytest_asyncio
import httpx
import json
import os
import time
import base64
from pathlib import Path
from unittest.mock import patch, MagicMock
from functools import wraps
import inspect

from fastapi.testclient import TestClient
from persai.server import get_server
from llama_stack.distribution.library_client import AsyncLlamaStackAsLibraryClient
from llama_stack_client.lib.agents.agent import AsyncAgent
from persai.server.token_validator import ValidationResult

TEST_MODEL = "llama3.2:3b-instruct-fp16"

app = get_server()


def create_test_jwt_cookies():
    """Create valid JWT cookies for integration testing"""
    # Create a token that expires in 2 hours
    future_time = int(time.time()) + 7200
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": "integration-test-user", "exp": future_time}

    header_encoded = (
        base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    )
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )

    # Create a proper refresh token JWT
    refresh_payload = {
        "sub": "integration-test-user",
        "exp": future_time + 3600,
    }  # Refresh token expires later
    refresh_payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(refresh_payload).encode())
        .decode()
        .rstrip("=")
    )
    refresh_token = (
        f"{header_encoded}.{refresh_payload_encoded}.integration-test-refresh-signature"
    )

    return {
        "jwtPayload": f"{header_encoded}.{payload_encoded}",
        "jwtSignature": "integration-test-signature",
        "jwtRefreshToken": refresh_token,
    }


# Use test model instead of production model
TEST_SYSTEM_PROMPT = """\
You are a Prometheus expert, answering questions about Kubernetes and OpenShift cluster questions.

Make sure to use the available tools to get the list of available metrics.
DON'T USE metrics not received from the tools first.

ALERTS use "alertstate" label to indicate the firing state.

Try to use the metrics also to answer questions about the Kubernetes, if possible with the metrics.

Don't describe raw outputs of the time-series data. Provide only a human-readable summary.
"""


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def ollama_base_url():
    """Get Ollama base URL from environment or default."""
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


@pytest_asyncio.fixture(scope="session")
async def wait_for_ollama(ollama_base_url):
    """Wait for Ollama service to be ready."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{ollama_base_url}/api/tags")
            if response.status_code == 200:
                # Check if our model is available
                models = response.json()
                model_names = [model["name"] for model in models.get("models", [])]
                if TEST_MODEL in model_names:
                    yield True
                    return
                else:
                    raise RuntimeError(f"Model {TEST_MODEL} not available")
            else:
                await asyncio.sleep(10)
        except httpx.HTTPError as e:
            raise RuntimeError(
                f"Ollama service not ready: {type(e).__name__}: {str(e)}"
            )


@pytest.fixture
def llamastack_config():
    """LlamaStack configuration for integration tests."""
    return {
        "inference_provider": "ollama",
        "model_id": TEST_MODEL,
        "ollama_base_url": "http://localhost:11434",
        "agent_config": {
            "model": TEST_MODEL,
            "instructions": """You are a Prometheus expert AI assistant. You help users understand and query Prometheus metrics for Kubernetes and OpenShift clusters.

You have access to tools that can:
1. List available Prometheus metrics
2. Execute PromQL queries

When users ask about metrics or monitoring, use these tools to provide accurate, data-driven responses.""",
            "max_turns": 10,
            "enable_session_persistence": True,
            "tool_choice": "auto",
            "tool_prompt_format": "json",
        },
    }


@pytest_asyncio.fixture
async def test_config_path():
    """Path to test llamastack configuration."""
    return os.path.join(os.path.dirname(__file__), "llamastack.test.yaml")


@pytest_asyncio.fixture
async def test_llamastack_client(test_config_path, wait_for_ollama):
    """Create real AsyncLlamaStackAsLibraryClient with test config."""
    # Ensure Ollama is ready (wait_for_ollama is a fixture that has already run)
    # wait_for_ollama will be True if ollama is ready

    # Create client with test config
    client = AsyncLlamaStackAsLibraryClient(test_config_path)
    await client.initialize()

    yield client

    # Cleanup - no explicit cleanup needed for library client


@pytest_asyncio.fixture
async def test_agent(test_llamastack_client):
    """Create real AsyncAgent with test LlamaStack client."""
    from persai.agent.tools import promtools
    from llama_stack_client.types.shared_params.agent_config import AgentConfig

    # Clean up any existing agents
    for a in (await test_llamastack_client.agents.list()).data:
        await test_llamastack_client.agents.delete(agent_id=a["agent_id"])

    agent_config = AgentConfig(
        name="test-persai", model=TEST_MODEL, instructions=TEST_SYSTEM_PROMPT
    )

    agent = AsyncAgent(
        test_llamastack_client,  # type: ignore[arg-type]
        model=agent_config["model"],
        instructions=agent_config["instructions"],
        tools=promtools,
    )

    agent.agent_config["name"] = agent_config["name"]
    await agent.initialize()

    yield agent

    # Cleanup - agent cleanup handled by client


def use_test_llamastack(func):
    """Decorator to connect the app to local test llamastack."""

    # The implementation is a bit hairy because we try to be transparent
    # about the used fixtures for the wrapped function. That means we need
    # to add the requested fixtures to the signature of the wrapped function
    # and then filter it out inside the method.
    sig = inspect.signature(func)
    params = list(sig.parameters.values())

    # Add fixture parameters if they don't exist
    fixture_names = ["test_llamastack_client", "test_agent"]
    existing_param_names = [p.name for p in params]

    for fixture_name in fixture_names:
        if fixture_name not in existing_param_names:
            params.append(
                inspect.Parameter(fixture_name, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            )

    # Create new signature with added parameters
    new_sig = sig.replace(parameters=params)

    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Extract fixtures from kwargs
        test_llamastack_client_fixture = kwargs.get("test_llamastack_client")
        test_agent_fixture = kwargs.get("test_agent")

        # Filter out the fixture parameters from kwargs before calling original function
        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in fixture_names}

        # Mock the initialize function to do nothing (tests will set up their own clients)
        async def mock_initialize():
            pass

        with patch(
            "persai.server.endpoints.get_async_client",
            return_value=test_llamastack_client_fixture,
        ), patch(
            "persai.server.endpoints.get_agent", return_value=test_agent_fixture
        ), patch(
            "persai.agent.agent.initialize", side_effect=mock_initialize
        ):
            return await func(*args, **filtered_kwargs)

    # Apply the new signature to the wrapper
    wrapper.__signature__ = new_sig  # type: ignore
    return wrapper


@pytest.fixture(autouse=True)
def mock_token_validator_integration():
    """Mock the token validator for integration tests to return successful validation."""
    with patch(
        "persai.server.token_validator.get_token_validator"
    ) as mock_get_validator:
        mock_validator = MagicMock()
        mock_validator.validate_auth_info.return_value = ValidationResult(
            is_valid=True, validated_at=time.time()
        )
        mock_get_validator.return_value = mock_validator
        yield mock_validator


@pytest_asyncio.fixture
async def test_client():
    """Create test client for FastAPI app with origin header simulation."""
    from httpx import ASGITransport

    # Default headers to simulate requests coming from Perses UI
    default_headers = {"origin": "http://perses.example.com"}

    # Add authentication cookies for integration tests
    auth_cookies = create_test_jwt_cookies()

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers=default_headers,
        cookies=auth_cookies,
    ) as client:
        yield client


@pytest.fixture
def sync_test_client():
    """Create synchronous test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def fixtures_path():
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def test_conversations(fixtures_path):
    """Load test conversation fixtures."""
    with open(fixtures_path / "test_conversations.json", "r") as f:
        return json.load(f)


@pytest.fixture
def agent_configs(fixtures_path):
    """Load agent configuration fixtures."""
    with open(fixtures_path / "agent_configs.json", "r") as f:
        return json.load(f)
