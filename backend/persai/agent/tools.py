from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from contextvars import ContextVar
import time
from datetime import datetime, timedelta

import dotenv
import requests
from loguru import logger

from llama_stack_client.lib.agents.client_tool import client_tool
from persai.server.auth import AuthInfo, parse_jwt_payload
from persai.errors import PrometheusError, ConfigurationError

dotenv.load_dotenv()

# Token refresh threshold - 1 minute before expiration
TOKEN_REFRESH_THRESHOLD = 60


@dataclass
class ToolContext:
    """Context information passed to tools from API requests."""

    prometheus_url: str
    auth: AuthInfo


# ContextVar for storing request-specific tool context
tool_context: ContextVar[Optional[ToolContext]] = ContextVar(
    "tool_context", default=None
)


class PrometheusClient:
    def __init__(self, base_url: str, auth_info: Optional[AuthInfo] = None):
        self.base_url = base_url.rstrip("/")
        self.auth_info = auth_info

    def ensure_valid_token(self) -> Optional[AuthInfo]:
        """
        Ensure the auth token is valid, refreshing it if necessary.
        Returns updated AuthInfo if refresh occurred, None if no auth or refresh failed.
        """
        # This can happen when PERSAI_AUTH=false
        if not self.auth_info or not self.auth_info.auth_token:
            return None

        # Check if token needs refresh
        if not self.auth_info.auth_token_should_refresh(TOKEN_REFRESH_THRESHOLD):
            return None  # Token is still valid

        # Token needs refresh
        if not self.auth_info.refresh_token:
            logger.warning("Auth token expired but no refresh token available")
            return None

        try:
            return self._refresh_token()
        except Exception as e:
            logger.exception("Failed to refresh auth token", error=str(e))
            return None

    def _refresh_token(self) -> AuthInfo:
        """
        Call the Perses refresh endpoint to get a new access token.
        """
        refresh_url = f"{self.auth_info.perses_url}/api/auth/refresh"

        logger.info("Refreshing auth token", refresh_url=refresh_url)

        response = requests.post(
            refresh_url,
            json={"refresh_token": self.auth_info.refresh_token},
            headers={"Content-Type": "application/json"},
        )

        response.raise_for_status()
        token_data = response.json()

        new_payload = parse_jwt_payload(token_data["access_token"])

        # Create updated AuthInfo with new access token
        updated_auth = AuthInfo(
            auth_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token", self.auth_info.refresh_token),
            perses_url=self.auth_info.perses_url,
            payload=new_payload,
        )

        # Update our auth info
        self.auth_info = updated_auth

        logger.info("Auth token refreshed successfully")
        return updated_auth

    def _get_headers(self) -> dict:
        """Generate headers with current auth token"""
        headers = {}
        if self.auth_info and self.auth_info.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_info.auth_token}"
        return headers

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Wrapper for requests.get/post with structured logging and response handling"""
        # Ensure token is valid before making request
        updated_auth = self.ensure_valid_token()
        if updated_auth:
            # Update context with refreshed auth info
            ctx = tool_context.get()
            if ctx:
                ctx.auth = updated_auth
                tool_context.set(ctx)

        kwargs["headers"] = {**self._get_headers(), **kwargs.get("headers", {})}
        url = f"{self.base_url}/{endpoint}"

        with logger.contextualize(endpoint=endpoint, method=method):
            logger.debug(f"Making Prometheus request", method=method, url=url)

            start_time = time.time()
            try:
                if method == "GET":
                    response = requests.get(url, **kwargs)
                else:
                    response = requests.post(url, **kwargs)

                duration_ms = (time.time() - start_time) * 1000

                logger.info(
                    "Prometheus request completed",
                    status_code=response.status_code,
                    duration_ms=round(duration_ms, 2),
                    response_size=len(response.content),
                )

                self._raise_for_status(response)

                result = response.json()

                return result["data"]
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.exception(
                    "Prometheus request failed",
                    duration_ms=round(duration_ms, 2),
                    error_type=type(e).__name__,
                    error=str(e),
                )
                raise

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Internal GET request method"""
        return self._request("GET", endpoint, params=params)

    def _post(self, endpoint: str, data: dict, headers: Optional[dict] = None) -> dict:
        """Internal POST request method"""
        return self._request("POST", endpoint, data=data, headers=headers)

    def _raise_for_status(self, response):
        """Raise HTTPError based on response status

        Enhanced version over `requests` to include response from the server: can be used
        by LLM to tweak the response"""

        if 400 <= response.status_code:
            http_error_msg = f"{response.status_code} Error: {response.reason}"

            if response.content:
                http_error_msg += "\n" + str(response.content)

            raise requests.HTTPError(http_error_msg, response=response)

        response.raise_for_status()

    def list_metrics(self) -> List[str]:
        """List all available metrics in Prometheus"""
        return self._get("label/__name__/values")

    def execute_range_query(
        self, query: str, start: str, end: str, step: str
    ) -> Dict[str, Any]:
        """Execute a PromQL range query"""
        data = self._post(
            "query_range",
            data={"query": query, "start": start, "end": end, "step": step},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return {"resultType": data["resultType"], "result": data["result"]}


def get_prometheus_client() -> PrometheusClient:
    """Get a PrometheusClient configured from the current context"""
    ctx = tool_context.get()
    if not ctx or not ctx.prometheus_url:
        raise ConfigurationError("No Prometheus URL configured in context")
    return PrometheusClient(ctx.prometheus_url, ctx.auth)


@client_tool
async def list_metrics() -> List[str]:
    """List all available metrics in Prometheus.

    :returns: List of metric names as strings
    """
    return get_prometheus_client().list_metrics()


async def _execute_range_query(
    query: str,
    step: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    duration: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a PromQL range query with flexible time specification.

    see `execute_range_query` for docs.
    """
    if start and end and duration:
        raise ValueError("Cannot specify both start/end and duration parameters")

    if not start and not end and not duration:
        duration = "1h"

    if (start and not end) or (end and not start):
        raise ValueError("Both start and end must be provided together")

    if duration:
        end_time = datetime.now()
        start_time = end_time - _parse_duration(duration)

        start = start_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        end = end_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    with logger.contextualize(
        query=query, start=start, end=end, step=step, duration=duration
    ):
        logger.info("Executing range query")

        result = get_prometheus_client().execute_range_query(query, start, end, step)

        logger.info(
            "Range query completed",
            result_type=result["resultType"],
            result_count=len(result["result"]),
        )

        return result


@client_tool
async def execute_range_query(
    query: str,
    step: str,
    # not using Optional, as some LLM providers can't handle it (seen it with Gemini).
    start: str = None,  # pyright: ignore[reportArgumentType]
    end: str = None,  # pyright: ignore[reportArgumentType]
    duration: str = None,  # pyright: ignore[reportArgumentType]
) -> Dict[str, Any]:
    """Execute a PromQL range query with flexible time specification.

    For current/recent data queries, use the 'duration' parameter to specify how far back
    to look from now (e.g., '1h' for last hour, '30m' for last 30 minutes).

    For historical data queries, use explicit 'start' and 'end' times.

    :param query: PromQL query string
    :param step: Query resolution step width (e.g., '15s', '1m', '1h')
    :param start: Start time as RFC3339 or Unix timestamp (optional)
    :param end: End time as RFC3339 or Unix timestamp (optional)
    :param duration: Duration to look back from now (e.g., '1h', '30m', '1d', '2w') (optional)

    :returns: Range query result with type (usually matrix) and values over time

    Note: Either provide both 'start' and 'end', or provide 'duration'.
    If 'duration' is provided, it will query from (now - duration) to now.
    If neither is provided, defaults to last 1 hour.
    """
    # Need to wrap the function, as llamastack client tool
    # is not callable: `TypeError: '_WrappedTool' object is not callable`.
    # Might be worth fixing upstream.
    return await _execute_range_query(query, step, start, end, duration)


def _parse_duration(duration: str) -> timedelta:
    """Parse a duration string like '1h', '30m', '1d' into a timedelta object."""
    duration = duration.strip().lower()

    if duration.endswith("s"):
        return timedelta(seconds=int(duration[:-1]))
    elif duration.endswith("m"):
        return timedelta(minutes=int(duration[:-1]))
    elif duration.endswith("h"):
        return timedelta(hours=int(duration[:-1]))
    elif duration.endswith("d"):
        return timedelta(days=int(duration[:-1]))
    elif duration.endswith("w"):
        return timedelta(weeks=int(duration[:-1]))
    else:
        raise ValueError(
            f"Invalid duration format: {duration}. Use formats like '1h', '30m', '1d'"
        )


promtools = [list_metrics, execute_range_query]
