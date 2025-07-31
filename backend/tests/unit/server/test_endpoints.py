import pytest
import json
from io import StringIO

from httpx import AsyncClient
from llama_stack_client import APIConnectionError
from llama_stack_client.types.agents.session_create_response import (
    SessionCreateResponse,
)
from loguru import logger

from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_session_create_success(
    mock_get_agent, mock_agent, mock_get_async_client, mock_async_client, async_client
):
    # Arrange
    mock_agent.agent_id = "test_agent_id"
    mock_agent.extra_headers = {}

    session_response = SessionCreateResponse(session_id="new_session")
    mock_session_create = AsyncMock(return_value=session_response)
    mock_async_client.agents.session.create = mock_session_create

    # Act
    response = await async_client.post("/session")

    # Assert
    assert response.status_code == 201  # Fixed: endpoint returns 201 CREATED
    assert response.json() == {"session_id": "new_session"}
    mock_get_agent.assert_awaited_once()
    mock_get_async_client.assert_awaited_once()
    mock_session_create.assert_awaited_once_with(
        agent_id="test_agent_id", session_name="chat", extra_headers={}
    )


@pytest.mark.asyncio
async def test_session_create_connection_error(
    async_client: AsyncClient,
    mock_get_async_client,
) -> None:
    """Test API connection error for session creation."""
    # Arrange
    mock_get_async_client.side_effect = APIConnectionError(
        message="Connection failed", request=MagicMock()
    )

    # Act
    response = await async_client.post("/session")

    # Assert
    assert response.status_code == 503
    response_json = response.json()
    assert response_json["error"]["type"] == "LlamaStackConnectionError"
    assert response_json["error"]["message"] == "Unable to connect to Llama Stack"


@pytest.mark.asyncio
async def test_sessions_get_success(
    async_client, mock_agent, mock_async_client, mock_get_agent, mock_get_async_client
):
    # Arrange
    mock_agent.agent_id = "test_agent_id"

    # Mock the list response object with data attribute
    mock_list_response = MagicMock()
    mock_list_response.data = [
        {"session_id": "session1"},
        {"session_id": "session2"},
    ]

    mock_sessions_list = AsyncMock(return_value=mock_list_response)
    mock_async_client.agents.session.list = mock_sessions_list

    # Act
    response = await async_client.get("/sessions")

    # Assert
    assert response.status_code == 200
    assert response.json() == [{"session_id": "session1"}, {"session_id": "session2"}]
    mock_get_agent.assert_awaited_once()
    mock_get_async_client.assert_awaited_once()
    mock_sessions_list.assert_awaited_once_with(agent_id="test_agent_id")


@pytest.mark.asyncio
async def test_sessions_get_connection_error(
    async_client: AsyncClient,
    mock_get_agent,
) -> None:
    """Test API connection error for getting sessions."""
    # Arrange
    mock_get_agent.side_effect = APIConnectionError(
        message="Connection failed", request=MagicMock()
    )

    # Act
    response = await async_client.get("/sessions")

    # Assert
    assert response.status_code == 503
    response_json = response.json()
    assert response_json["error"]["type"] == "LlamaStackConnectionError"
    assert response_json["error"]["message"] == "Unable to connect to Llama Stack"


@pytest.mark.asyncio
async def test_session_delete_success(
    async_client,
    mock_async_client,
    mock_agent,
    mock_get_agent,
    mock_get_async_client,
):
    # Arrange
    session_id = "test_session_id"
    mock_agent.agent_id = "test_agent_id"

    mock_session_delete = AsyncMock(return_value={"success": True})
    mock_async_client.agents.session.delete = mock_session_delete

    # Act
    response = await async_client.delete(f"/session/{session_id}")

    # Assert
    assert response.status_code == 200
    assert response.json() == {"success": True}
    mock_get_agent.assert_awaited_once()
    mock_get_async_client.assert_awaited_once()
    mock_session_delete.assert_awaited_once_with(
        session_id=session_id, agent_id="test_agent_id"
    )


@pytest.mark.asyncio
async def test_session_delete_not_found(
    async_client,
    mock_async_client,
    mock_agent,
):
    # Arrange
    session_id = "non_existent_session"
    mock_agent.agent_id = "test_agent_id"

    # Mock delete to raise ValueError for not found
    mock_session_delete = AsyncMock(side_effect=ValueError("Session not found"))
    mock_async_client.agents.session.delete = mock_session_delete

    # Act
    response = await async_client.delete(f"/session/{session_id}")

    # Assert
    assert response.status_code == 404
    response_json = response.json()
    assert response_json["error"]["type"] == "HTTPException"
    assert response_json["error"]["message"]["response"] == "Session not found"


@pytest.mark.asyncio
async def test_session_delete_connection_error(
    async_client: AsyncClient,
    mock_get_async_client,
) -> None:
    """Test API connection error for session deletion."""
    # Arrange
    mock_get_async_client.side_effect = APIConnectionError(
        message="Connection failed", request=MagicMock()
    )

    # Act
    response = await async_client.delete("/session/some_id")

    # Assert
    assert response.status_code == 503
    response_json = response.json()
    assert response_json["error"]["type"] == "LlamaStackConnectionError"
    assert response_json["error"]["message"] == "Unable to connect to Llama Stack"


@pytest.mark.asyncio
async def test_session_turn_create_success(
    async_client,
    mock_agent,
    mock_async_client,
    mock_get_agent,
    mock_get_async_client,
    mock_sse_generator,
):
    # Arrange
    session_id = "test_session_id"
    request_data = {"message": "Hello"}

    mock_agent.agent_id = "test_agent_id"

    # Mock the session list to validate the session exists
    mock_list_response = MagicMock()
    mock_list_response.data = [
        {"session_id": session_id},
        {"session_id": "other_session"},
    ]

    mock_sessions_list = AsyncMock(return_value=mock_list_response)
    mock_async_client.agents.session.list = mock_sessions_list

    # Mock the create_turn response
    mock_turn_response = MagicMock()

    async def async_iterator():
        yield mock_turn_response

    mock_agent.create_turn.return_value = async_iterator()

    mock_sse_generator.return_value = "mock_sse_response"

    # Act
    response = await async_client.post(
        f"/session/{session_id}/turn?datasource_path=%2Fproxy%2Fsrc%2Fprometheus",
        json=request_data,
    )

    # Assert
    assert response.status_code == 200
    assert response.text == "mock_sse_response"
    mock_get_agent.assert_awaited_once()
    mock_get_async_client.assert_awaited_once()
    mock_sessions_list.assert_awaited_once_with(agent_id="test_agent_id")
    mock_agent.create_turn.assert_called_once()
    mock_sse_generator.assert_called_once()


@pytest.mark.asyncio
async def test_session_turn_create_session_not_found(
    async_client, mock_agent, mock_async_client
):
    # Arrange
    session_id = "non_existent_session"
    request_data = {"message": "Hello"}

    mock_agent.agent_id = "test_agent_id"

    # Mock the session list to not include the requested session
    mock_list_response = MagicMock()
    mock_list_response.data = [
        {"session_id": "other_session"},
    ]

    mock_sessions_list = AsyncMock(return_value=mock_list_response)
    mock_async_client.agents.session.list = mock_sessions_list

    # Act
    response = await async_client.post(
        f"/session/{session_id}/turn?datasource_path=%2Fproxy%2Fsrc%2Fprometheus",
        json=request_data,
    )

    # Assert
    assert response.status_code == 404
    response_json = response.json()
    assert response_json["error"]["type"] == "HTTPException"
    assert response_json["error"]["message"]["response"] == "Session not found"


@pytest.mark.asyncio
async def test_session_turn_create_connection_error(
    async_client: AsyncClient,
    mock_get_agent,
) -> None:
    """Test API connection error for creating a session turn."""
    # Arrange

    mock_get_agent.side_effect = APIConnectionError(
        message="Connection failed", request=MagicMock()
    )
    payload = {"message": "Hello"}

    # Act
    response = await async_client.post(
        "/session/some_id/turn?datasource_path=%2Fproxy%2Fsrc%2Fprometheus",
        json=payload,
    )

    # Assert
    assert response.status_code == 503
    response_json = response.json()
    assert response_json["error"]["type"] == "LlamaStackConnectionError"
    assert response_json["error"]["message"] == "Unable to connect to Llama Stack"


@pytest.mark.asyncio
async def test_session_delete_logging_context(
    async_client,
    mock_async_client,
    mock_agent,
):
    """Test that session_id appears in logging context for session_delete endpoint."""
    # Arrange
    session_id = "test_session_123"
    mock_agent.agent_id = "test_agent_id"
    mock_session_delete = AsyncMock(return_value={"success": True})
    mock_async_client.agents.session.delete = mock_session_delete

    # Capture log output
    log_capture = StringIO()
    handler_id = logger.add(log_capture, format="{message}", serialize=True)

    try:
        # Act
        response = await async_client.delete(f"/session/{session_id}")

        # Assert response is successful
        assert response.status_code == 200
        assert response.json() == {"success": True}

        # Check that session_id appears in logging context
        log_output = log_capture.getvalue()
        log_lines = [line.strip() for line in log_output.split("\n") if line.strip()]

        # Find a log entry with session_id in the context
        session_id_found = False
        for line in log_lines:
            try:
                log_entry = json.loads(line)
                extra = log_entry.get("record", {}).get("extra", {})
                if extra.get("session_id") == session_id:
                    session_id_found = True
                    break
            except json.JSONDecodeError:
                continue

        assert session_id_found, "session_id should appear in logging context"

    finally:
        # Clean up the test handler
        logger.remove(handler_id)


@pytest.mark.asyncio
async def test_session_turn_create_accepts_new_parameters(
    async_client,
    mock_agent,
    mock_async_client,
    mock_get_agent,
    mock_get_async_client,
    mock_sse_generator,
):
    """Test that session_turn_create accepts auth token and datasource parameters without errors."""

    # Arrange
    session_id = "test_session_id"
    request_data = {"message": "Hello"}
    auth_token = "test-auth-token"
    datasource_path = "/proxy/src/prometheus"

    mock_agent.agent_id = "test_agent_id"

    # Mock the session list to validate the session exists
    mock_list_response = MagicMock()
    mock_list_response.data = [{"session_id": session_id}]
    mock_sessions_list = AsyncMock(return_value=mock_list_response)
    mock_async_client.agents.session.list = mock_sessions_list

    # Mock create_turn to return async iterator
    async def mock_create_turn(*args, **kwargs):
        async def async_iterator():
            yield MagicMock()

        return async_iterator()

    mock_agent.create_turn = mock_create_turn
    mock_sse_generator.return_value = "mock_sse_response"

    # Act
    response = await async_client.post(
        f"/session/{session_id}/turn",
        json=request_data,
        headers={"X-Auth-Token": auth_token},
        params={"datasource_path": datasource_path},
    )

    # Assert
    assert response.status_code == 200
    assert response.text == "mock_sse_response"
