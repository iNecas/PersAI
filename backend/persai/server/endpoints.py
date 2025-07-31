import functools
from typing import Any, AsyncIterator, Callable, Coroutine

from llama_stack.distribution.server.server import sse_generator
from llama_stack_client.types import UserMessage  # type: ignore

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from loguru import logger

from persai.agent import get_agent, get_async_client
from persai.agent import tool_context, ToolContext
from .token_validator import get_auth_info

router = APIRouter(tags=["streaming_query"])


def with_session_logging(
    func: Callable[..., Coroutine[Any, Any, Any]],
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Decorator that adds session_id to logging context for session-based endpoints."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Extract session_id from kwargs (FastAPI puts path parameters in kwargs)
        session_id = kwargs.get("session_id")

        if session_id:
            with logger.contextualize(session_id=session_id):
                return await func(*args, **kwargs)
        else:
            return await func(*args, **kwargs)

    return wrapper


@router.post("/session", status_code=status.HTTP_201_CREATED)
async def session_create():
    """Creates a new agent session."""
    logger.info("Creating new session")
    client = await get_async_client()
    agent = await get_agent()
    session = await client.agents.session.create(
        agent_id=agent.agent_id, session_name="chat", extra_headers=agent.extra_headers
    )
    logger.info("Session created successfully", session_id=session.session_id)
    return session


@router.get("/sessions")
async def sessions_get():
    """Retrieves all sessions associated with the current agent."""
    logger.info("Retrieving all sessions")
    client = await get_async_client()
    agent = await get_agent()
    sessions = await client.agents.session.list(agent_id=agent.agent_id)
    logger.info("Sessions retrieved successfully", session_count=len(sessions.data))
    return sessions.data


@router.delete("/session/{session_id}")
@with_session_logging
async def session_delete(session_id: str):
    """Deletes a specific agent session by its ID."""
    logger.info("Deleting session")
    client = await get_async_client()
    agent = await get_agent()

    try:
        result = await client.agents.session.delete(
            session_id=session_id, agent_id=agent.agent_id
        )
        logger.info("Session deleted successfully")
        return result
    except ValueError as e:
        logger.warning("Session not found for deletion")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "response": "Session not found",
            },
        ) from e


@router.post("/session/{session_id}/turn")
@with_session_logging
async def session_turn_create(
    session_id: str,
    body: dict,
    datasource_path: str,
    auth_info=Depends(get_auth_info),
) -> StreamingResponse:
    """Creates a new turn (message) within a specific agent session."""
    message = body.get("message", "")
    logger.info("Creating turn", message_length=len(message))

    # Construct Prometheus URL using auth info
    if not datasource_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"response": "No datasource path provided"},
        )

    prometheus_url = f"{auth_info.perses_url}{datasource_path}/api/v1"

    # Set context to be used in the tool calls
    tool_context.set(
        ToolContext(
            prometheus_url=prometheus_url,
            auth=auth_info,
        )
    )

    agent = await get_agent()
    client = await get_async_client()

    # Validate session exists before creating turn
    sessions = await client.agents.session.list(agent_id=agent.agent_id)
    valid_session_ids = [s["session_id"] for s in sessions.data]
    if session_id not in valid_session_ids:
        logger.warning("Session not found for turn creation")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "response": f"Session not found",
            },
        )

    logger.info("Starting turn creation")
    response: AsyncIterator = agent.create_turn(
        messages=[UserMessage(role="user", content=message)],
        session_id=session_id,
        stream=True,
    )

    return StreamingResponse(sse_generator(response), media_type="text/event-stream")
