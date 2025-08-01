import time
import json
import base64
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from persai.agent.tools import (
    tool_context,
    ToolContext,
    PrometheusClient,
    get_prometheus_client,
    _execute_range_query,
    _parse_duration,
)
from persai.server.auth import AuthInfo
from persai.errors.exceptions import PrometheusError, ConfigurationError


def create_jwt_token(
    payload: dict, header: dict = None, signature: str = "signature"
) -> str:
    """Helper function to create a JWT token for testing."""
    if header is None:
        header = {"alg": "HS256", "typ": "JWT"}

    header_encoded = (
        base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    )
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )

    return f"{header_encoded}.{payload_encoded}.{signature}"


def create_auth_info(
    exp_offset_seconds: int = 7200, refresh_token: str = "refresh-token"
) -> AuthInfo:
    """Helper function to create an AuthInfo instance for testing.

    Args:
        exp_offset_seconds: Seconds from now when the token expires (positive for future, negative for past)
        refresh_token: The refresh token to use
    """
    exp_time = int(time.time()) + exp_offset_seconds
    payload = {"sub": "user", "exp": exp_time}
    token = create_jwt_token(payload)

    return AuthInfo(
        auth_token=token,
        refresh_token=refresh_token,
        perses_url="http://perses.example.com",
        payload=payload,
    )


@pytest.fixture
def mock_prometheus_response():
    """Mock successful Prometheus response"""
    return {"status": "success", "data": {"resultType": "vector", "result": []}}


@pytest.fixture
def client():
    """PrometheusClient instance for testing"""
    auth_info = create_auth_info()  # Creates token that expires in 2 hours
    return PrometheusClient("http://prometheus:9090/api/v1", auth_info)


@pytest.fixture
def client_no_auth():
    """PrometheusClient instance without auth for testing"""
    return PrometheusClient("http://prometheus:9090/api/v1")


@pytest.fixture
def mocked_range_query_result():
    """Common expected result structure for matrix queries"""
    return {"resultType": "matrix", "result": [{"metric": {}, "values": []}]}


@pytest.fixture
def mock_prometheus_client(mocked_range_query_result):
    """Mock PrometheusClient for testing tool functions with patching"""
    mock_client = MagicMock()
    mock_client.execute_range_query.return_value = mocked_range_query_result
    with patch("persai.agent.tools.get_prometheus_client") as mock_get_client:
        mock_get_client.return_value = mock_client
        yield mock_client


@pytest.fixture
def tool_context_with_auth():
    """ToolContext with authentication for testing"""
    ctx = ToolContext(
        prometheus_url="http://prometheus:9090/api/v1",
        auth=create_auth_info(),
    )
    tool_context.set(ctx)
    return ctx


@pytest.fixture
def tool_context_no_auth():
    """ToolContext without authentication for testing"""
    ctx = ToolContext(
        prometheus_url="http://prometheus:9090/api/v1",
        auth=AuthInfo(
            auth_token=None,
            refresh_token=None,
            perses_url="http://perses.example.com",
            payload=None,
        ),
    )
    tool_context.set(ctx)
    return ctx


@pytest.fixture
def fixed_datetime():
    """Fixed datetime for testing duration calculations"""
    with patch("persai.agent.tools.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.strftime = datetime.strftime
        yield


def test_client_initialization():
    """Test client initialization with and without auth"""
    auth_info = create_auth_info()
    client_with_auth = PrometheusClient("http://prometheus:9090/api/v1", auth_info)
    assert client_with_auth.base_url == "http://prometheus:9090/api/v1"
    assert (
        client_with_auth._get_headers()["Authorization"]
        == f"Bearer {auth_info.auth_token}"
    )
    assert client_with_auth.auth_info == auth_info

    client_no_auth = PrometheusClient("http://prometheus:9090/api/v1/")
    assert client_no_auth.base_url == "http://prometheus:9090/api/v1"
    assert "Authorization" not in client_no_auth._get_headers()
    assert client_no_auth.auth_info is None


def test_list_metrics(client, mock_prometheus_response):
    """Test list_metrics method"""
    mock_response_data = ["metric1", "metric2", "metric3"]
    mock_prometheus_response["data"] = mock_response_data

    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = mock_prometheus_response
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = client.list_metrics()

        assert result == mock_response_data
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        assert "Authorization" in kwargs["headers"]
        # Check that the authorization header contains the client's token
        assert (
            kwargs["headers"]["Authorization"]
            == f"Bearer {client.auth_info.auth_token}"
        )


def test_execute_range_query(client, mock_prometheus_response):
    """Test execute_range_query method"""
    mock_data = {"resultType": "matrix", "result": [{"metric": {}, "values": []}]}
    mock_prometheus_response["data"] = mock_data

    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = mock_prometheus_response
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = client.execute_range_query(
            "up", "2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z", "1m"
        )

        expected_result = {
            "resultType": "matrix",
            "result": [{"metric": {}, "values": []}],
        }
        assert result == expected_result

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert "Authorization" in kwargs["headers"]
        # Check that the authorization header contains the client's token
        assert (
            kwargs["headers"]["Authorization"]
            == f"Bearer {client.auth_info.auth_token}"
        )
        assert kwargs["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
        assert kwargs["data"]["query"] == "up"


def test_client_without_auth(client_no_auth, mock_prometheus_response):
    """Test client methods work without auth token"""
    mock_response_data = ["metric1", "metric2"]
    mock_prometheus_response["data"] = mock_response_data

    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = mock_prometheus_response
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = client_no_auth.list_metrics()

        assert result == mock_response_data
        _, kwargs = mock_get.call_args
        assert "Authorization" not in kwargs["headers"]


def test_prometheus_api_error(client):
    """Test handling of Prometheus API errors"""
    error_response = {"status": "error", "error": "Invalid query"}

    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = error_response
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        with pytest.raises(
            PrometheusError, match="Prometheus API error: Invalid query"
        ):
            client.list_metrics()


def test_get_prometheus_client_factory(tool_context_with_auth):
    """Test get_prometheus_client factory function"""
    client = get_prometheus_client()
    assert isinstance(client, PrometheusClient)
    assert client.base_url == "http://prometheus:9090/api/v1"
    assert (
        client._get_headers()["Authorization"]
        == f"Bearer {tool_context_with_auth.auth.auth_token}"
    )
    assert client.auth_info == tool_context_with_auth.auth


def test_get_prometheus_client_no_context():
    """Test get_prometheus_client raises error when no context"""
    tool_context.set(None)

    with pytest.raises(
        ConfigurationError, match="No Prometheus URL configured in context"
    ):
        get_prometheus_client()


def test_ensure_valid_token_no_auth():
    """Test ensure_valid_token with no auth info"""
    client = PrometheusClient("http://prometheus:9090/api/v1")
    result = client.ensure_valid_token()
    assert result is None


def test_ensure_valid_token_valid_token():
    """Test ensure_valid_token with valid token"""
    auth_info = create_auth_info()  # Creates token that expires in 2 hours
    client = PrometheusClient("http://prometheus:9090/api/v1", auth_info)

    result = client.ensure_valid_token()
    assert result is None  # No refresh needed


@patch("requests.post")
def test_ensure_valid_token_refresh_success(mock_post):
    """Test ensure_valid_token successfully refreshes expired token"""
    # Create an expired AuthInfo
    expired_auth_info = create_auth_info(exp_offset_seconds=-3600)  # Expired 1 hour ago

    # Create a valid new JWT token for the refresh response
    new_auth_info = create_auth_info(exp_offset_seconds=7200)  # Expires in 2 hours
    new_token = new_auth_info.auth_token

    # Mock successful refresh response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": new_token,
        "refresh_token": "new-refresh-token",
    }
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    client = PrometheusClient("http://prometheus:9090/api/v1", expired_auth_info)

    result = client.ensure_valid_token()

    assert result is not None
    assert result.auth_token == new_token
    assert result.refresh_token == "new-refresh-token"
    assert client.auth_info.auth_token == new_token
    assert client._get_headers()["Authorization"] == f"Bearer {new_token}"

    mock_post.assert_called_once_with(
        "http://perses.example.com/api/auth/refresh",
        json={"refresh_token": "refresh-token"},
        headers={"Content-Type": "application/json"},
    )


@patch("requests.post")
def test_ensure_valid_token_refresh_failure(mock_post):
    """Test ensure_valid_token handles refresh failure"""
    # Create an expired AuthInfo
    expired_auth_info = create_auth_info(exp_offset_seconds=-3600)  # Expired 1 hour ago

    # Mock failed refresh response
    mock_post.side_effect = Exception("Refresh failed")

    client = PrometheusClient("http://prometheus:9090/api/v1", expired_auth_info)

    result = client.ensure_valid_token()

    assert result is None  # Refresh failed


def test_get_prometheus_client_no_auth(tool_context_no_auth):
    """Test get_prometheus_client factory function with no auth"""
    client = get_prometheus_client()
    assert isinstance(client, PrometheusClient)
    assert client.base_url == "http://prometheus:9090/api/v1"
    assert "Authorization" not in client._get_headers()
    assert client.auth_info.auth_token is None


def test_parse_duration():
    """Test _parse_duration helper function"""
    assert _parse_duration("30s") == timedelta(seconds=30)
    assert _parse_duration("5m") == timedelta(minutes=5)
    assert _parse_duration("2h") == timedelta(hours=2)
    assert _parse_duration("1d") == timedelta(days=1)
    assert _parse_duration("1w") == timedelta(weeks=1)

    # Test case insensitive
    assert _parse_duration("30S") == timedelta(seconds=30)
    assert _parse_duration("5M") == timedelta(minutes=5)

    # Test with whitespace
    assert _parse_duration(" 30s ") == timedelta(seconds=30)

    # Test invalid format
    with pytest.raises(ValueError, match="Invalid duration format"):
        _parse_duration("30x")


@pytest.mark.asyncio
async def test_execute_range_query_with_duration(
    mock_prometheus_client,
    tool_context_with_auth,
    fixed_datetime,
    mocked_range_query_result,
):
    """Test execute_range_query with duration parameter"""
    result = await _execute_range_query("up", "1m", duration="1h")

    assert result == mocked_range_query_result

    # Verify that the client was called with calculated start/end times
    mock_prometheus_client.execute_range_query.assert_called_once()
    args = mock_prometheus_client.execute_range_query.call_args[0]
    query, start, end, step = args

    assert query == "up"
    assert step == "1m"
    # Start should be 1 hour before the fixed time
    assert start == "2024-01-01T11:00:00.000000Z"
    assert end == "2024-01-01T12:00:00.000000Z"


@pytest.mark.asyncio
async def test_execute_range_query_with_start_end(
    mock_prometheus_client, tool_context_with_auth, mocked_range_query_result
):
    """Test execute_range_query with explicit start/end parameters"""
    result = await _execute_range_query(
        "up", "1m", start="2024-01-01T00:00:00Z", end="2024-01-01T01:00:00Z"
    )

    assert result == mocked_range_query_result

    # Verify that the client was called with provided start/end times
    mock_prometheus_client.execute_range_query.assert_called_once_with(
        "up", "2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z", "1m"
    )


@pytest.mark.asyncio
async def test_execute_range_query_default_duration(
    mock_prometheus_client, tool_context_with_auth, fixed_datetime
):
    """Test execute_range_query defaults to 1h when no time params provided"""
    # Override the default return value for this test
    mock_prometheus_client.execute_range_query.return_value = {
        "resultType": "matrix",
        "result": [],
    }

    await _execute_range_query("up", "1m")

    # Verify that the client was called with 1h duration (default)
    mock_prometheus_client.execute_range_query.assert_called_once()
    args = mock_prometheus_client.execute_range_query.call_args[0]
    query, start, end, step = args

    assert query == "up"
    assert step == "1m"
    # Should default to 1h duration
    assert start == "2024-01-01T11:00:00.000000Z"
    assert end == "2024-01-01T12:00:00.000000Z"


@pytest.mark.asyncio
async def test_execute_range_query_validation_errors(tool_context_with_auth):
    """Test execute_range_query parameter validation"""
    # Test: Cannot provide both start/end and duration
    with pytest.raises(ValueError, match="Cannot specify both start/end and duration"):
        await _execute_range_query(
            "up",
            "1m",
            start="2024-01-01T00:00:00Z",
            end="2024-01-01T01:00:00Z",
            duration="1h",
        )

    # Test: Must provide both start and end together
    with pytest.raises(
        ValueError, match="Both start and end must be provided together"
    ):
        await _execute_range_query("up", "1m", start="2024-01-01T00:00:00Z")

    with pytest.raises(
        ValueError, match="Both start and end must be provided together"
    ):
        await _execute_range_query("up", "1m", end="2024-01-01T01:00:00Z")
