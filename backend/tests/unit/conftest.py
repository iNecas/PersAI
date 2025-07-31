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


def create_test_jwt_cookies(auth_exp_offset=7200, refresh_exp_offset=10800, sub="test-user"):
    """Create JWT cookies for testing with customizable expiration times
    
    Args:
        auth_exp_offset: Seconds from now when auth token expires (positive=future, negative=past)
        refresh_exp_offset: Seconds from now when refresh token expires (positive=future, negative=past)
        sub: Subject (user ID) for the JWT tokens
    """
    current_time = int(time.time())
    
    # Create auth token payload
    auth_payload = {"sub": sub, "exp": current_time + auth_exp_offset}
    
    # Create refresh token payload  
    refresh_payload = {"sub": sub, "exp": current_time + refresh_exp_offset}

    # Use the shared helper to create tokens
    auth_token = create_test_jwt_token(auth_payload, "test-signature")
    refresh_token = create_test_jwt_token(refresh_payload, "test-refresh-signature")
    
    # Split auth token for cookie format
    auth_parts = auth_token.split(".")

    return {
        "jwtPayload": f"{auth_parts[0]}.{auth_parts[1]}",
        "jwtSignature": auth_parts[2], 
        "jwtRefreshToken": refresh_token,
    }


def create_test_jwt_token(payload, signature="test-signature"):
    """Create a single JWT token for testing
    
    Args:
        payload: The JWT payload dictionary
        signature: The JWT signature string
    """
    header = {"alg": "HS256", "typ": "JWT"}
    header_encoded = (
        base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    )
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    return f"{header_encoded}.{payload_encoded}.{signature}"


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
