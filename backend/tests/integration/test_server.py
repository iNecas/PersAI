import pytest
from fastapi import status

from .conftest import use_test_llamastack


@pytest.mark.asyncio
@use_test_llamastack
async def test_create_session_success(test_client):
    """Test successful session creation."""
    response = await test_client.post("/session")

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert "session_id" in data
    # Session ID should be a string (actual session from ollama)
    assert isinstance(data["session_id"], str)
    assert len(data["session_id"]) > 0


@pytest.mark.asyncio
@use_test_llamastack
async def test_list_sessions_with_data(test_client):
    """Test listing sessions with existing sessions."""
    # First create a session to test listing
    # Create a test session
    create_response = await test_client.post("/session")
    assert create_response.status_code == status.HTTP_201_CREATED
    created_session = create_response.json()

    # Now list sessions
    response = await test_client.get("/sessions")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    # Check if our created session is in the list
    session_ids = [session["session_id"] for session in data]
    assert created_session["session_id"] in session_ids


@pytest.mark.asyncio
@use_test_llamastack
async def test_delete_session_success(test_client):
    """Test successful session deletion."""
    # First create a session to delete
    create_response = await test_client.post("/session")
    assert create_response.status_code == status.HTTP_201_CREATED
    session_data = create_response.json()
    session_id = session_data["session_id"]

    # Now delete the session
    response = await test_client.delete(f"/session/{session_id}")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
@use_test_llamastack
async def test_delete_nonexistent_session(test_client):
    """Test deleting a non-existent session."""
    response = await test_client.delete("/session/nonexistent-session-id")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert "error" in data
    assert data["error"]["type"] == "HTTPException"
    assert data["error"]["message"]["response"] == "Session not found"


@pytest.mark.asyncio
@use_test_llamastack
async def test_create_turn_success(test_client):
    """Test successful turn creation with real AI response."""
    # First create a session
    session_response = await test_client.post("/session")
    assert session_response.status_code == status.HTTP_201_CREATED
    session_data = session_response.json()
    session_id = session_data["session_id"]

    # Create a turn
    turn_data = {"message": "Hello, can you help me with Prometheus monitoring?"}
    turn_response = await test_client.post(
        f"/session/{session_id}/turn?datasource_path=%2Fproxy%2Fglobaldatasources%2Fprometheus",
        json=turn_data,
    )

    assert turn_response.status_code == status.HTTP_200_OK
    assert turn_response.headers["content-type"] == "text/event-stream; charset=utf-8"


@pytest.mark.asyncio
@use_test_llamastack
async def test_create_turn_invalid_session(test_client):
    """Test creating a turn with invalid session ID."""
    turn_data = {"message": "Hello"}
    response = await test_client.post(
        "/session/invalid-session-id/turn?datasource_path=%2Fproxy%2Fglobaldatasources%2Fprometheus",
        json=turn_data,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert "error" in data
    assert data["error"]["type"] == "HTTPException"
    assert data["error"]["message"]["response"] == "Session not found"


@pytest.mark.asyncio
@use_test_llamastack
async def test_create_turn_empty_message(test_client):
    """Test creating a turn with empty message."""
    # First create a session
    session_response = await test_client.post("/session")
    assert session_response.status_code == status.HTTP_201_CREATED
    session_data = session_response.json()
    session_id = session_data["session_id"]

    # Try to create a turn with empty message
    turn_data = {"message": ""}
    response = await test_client.post(
        f"/session/{session_id}/turn?datasource_path=%2Fproxy%2Fglobaldatasources%2Fprometheus",
        json=turn_data,
    )

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
@use_test_llamastack
async def test_create_turn_missing_message(test_client):
    """Test creating a turn with missing message field."""
    # First create a session
    session_response = await test_client.post("/session")
    assert session_response.status_code == status.HTTP_201_CREATED
    session_data = session_response.json()
    session_id = session_data["session_id"]

    # Try to create a turn without message
    turn_data = {}
    response = await test_client.post(
        f"/session/{session_id}/turn?datasource_path=%2Fproxy%2Fglobaldatasources%2Fprometheus",
        json=turn_data,
    )

    assert response.status_code == status.HTTP_200_OK
