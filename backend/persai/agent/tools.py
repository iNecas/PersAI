from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from contextvars import ContextVar
import time

import dotenv
import requests
from loguru import logger

from llama_stack_client.lib.agents.client_tool import client_tool
from persai.server.auth import AuthInfo, parse_jwt_payload
from persai.errors import PrometheusError, ConfigurationError, CredentialsError

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

                response.raise_for_status()
                result = response.json()

                if result["status"] != "success":
                    raise PrometheusError(
                        f"Prometheus API error: {result.get('error', 'Unknown error')}"
                    )

                return result["data"]
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.exception(
                    "Prometheus request failed",
                    duration_ms=round(duration_ms, 2),
                    error_type=type(e).__name__,
                )
                raise

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Internal GET request method"""
        return self._request("GET", endpoint, params=params)

    def _post(self, endpoint: str, data: dict, headers: Optional[dict] = None) -> dict:
        """Internal POST request method"""
        return self._request("POST", endpoint, data=data, headers=headers)

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


@client_tool
async def execute_range_query(
    query: str, start: str, end: str, step: str
) -> Dict[str, Any]:
    """Execute a PromQL range query with start time, end time, and step interval

    :param query: PromQL query string
    :param start: Start time as RFC3339 or Unix timestamp
    :param end: End time as RFC3339 or Unix timestamp
    :param step: Query resolution step width (e.g., '15s', '1m', '1h')

    :returns: Range query result with type (usually matrix) and values over time
    """
    with logger.contextualize(query=query, start=start, end=end, step=step):
        logger.info("Executing range query")

        result = get_prometheus_client().execute_range_query(query, start, end, step)

        logger.info(
            "Range query completed",
            result_type=result["resultType"],
            result_count=len(result["result"]),
        )

        return result


promtools = [list_metrics, execute_range_query]
