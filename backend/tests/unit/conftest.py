import os
import json
import time
import base64
import pytest
import pytest_asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport

from persai.server.server import get_server
from persai.server.token_validator import ValidationResult


def create_test_jwt_cookies():
    """Create valid JWT cookies for testing"""
    # Create a token that expires in 2 hours
    future_time = int(time.time()) + 7200
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": "test-user", "exp": future_time}

    header_encoded = (
        base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    )
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )

    # Create a proper refresh token JWT
    refresh_payload = {"sub": "test-user", "exp": future_time + 3600}  # Refresh token expires later
    refresh_payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(refresh_payload).encode()).decode().rstrip("=")
    )
    refresh_token = f"{header_encoded}.{refresh_payload_encoded}.test-refresh-signature"

    return {
        "jwtPayload": f"{header_encoded}.{payload_encoded}",
        "jwtSignature": "test-signature",
        "jwtRefreshToken": refresh_token,
    }


@pytest.fixture(autouse=True)
def mock_token_validator():
    """Mock the token validator to return successful validation for all tests."""
    with patch("persai.server.token_validator.get_token_validator") as mock_get_validator:
        mock_validator = MagicMock()
        mock_validator.validate_auth_info.return_value = ValidationResult(
            is_valid=True,
            validated_at=time.time()
        )
        mock_get_validator.return_value = mock_validator
        yield mock_validator


@asynccontextmanager
async def create_async_client(env_vars=None, headers=None, cookies=None):
    """Factory function to create async clients with different server configurations."""
    if env_vars is None:
        env_vars = {}
    
    with patch.dict(os.environ, env_vars, clear=True), \
         patch("persai.agent.agent.initialize", new_callable=MagicMock):
        app = get_server()
        
        # Use provided headers/cookies or defaults
        client_headers = headers or {}
        client_cookies = cookies or {}
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers=client_headers,
            cookies=client_cookies
        ) as client:
            yield client


@pytest_asyncio.fixture
async def async_client():
    """Standard async client fixture for endpoint testing with authentication."""
    # Default headers to simulate requests coming from Perses UI
    default_headers = {"origin": "http://perses.example.com"}
    
    # Default cookies for authentication
    auth_cookies = create_test_jwt_cookies()
    
    # Use the factory with default endpoint testing configuration
    async with create_async_client(
        env_vars={},  # Use default environment
        headers=default_headers,
        cookies=auth_cookies
    ) as client:
        yield client


@pytest.fixture
def mock_sse_generator():
    with patch("persai.server.endpoints.sse_generator") as mock:
        yield mock


@pytest.fixture(autouse=True)
def mock_llamastack_functions():
    """Automatically mock get_async_client and get_agent for all unit tests.

    This fixture is automatically applied to all unit tests. To disable it for
    specific tests, you can:
    1. Use @pytest.mark.parametrize("mock_llamastack_functions", [None])
    2. Override the fixture in your test file with a non-autouse version
    """
    with patch("persai.server.endpoints.get_async_client") as mock_get_async_client, patch(
        "persai.server.endpoints.get_agent"
    ) as mock_get_agent:

        # Set up default return values
        mock_async_client = AsyncMock()
        mock_get_async_client.return_value = mock_async_client

        mock_agent = AsyncMock()
        mock_get_agent.return_value = mock_agent

        yield {
            "get_async_client": mock_get_async_client,
            "get_agent": mock_get_agent,
            "async_client": mock_async_client,
            "agent": mock_agent,
        }


@pytest.fixture
def mock_get_agent(mock_llamastack_functions):
    return mock_llamastack_functions["get_agent"]


@pytest.fixture
def mock_agent(mock_llamastack_functions):
    return mock_llamastack_functions["agent"]


@pytest.fixture
def mock_get_async_client(mock_llamastack_functions):
    return mock_llamastack_functions["get_async_client"]


@pytest.fixture
def mock_async_client(mock_llamastack_functions):
    return mock_llamastack_functions["async_client"]
