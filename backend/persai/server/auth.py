import json
import base64
import os
import time
from functools import cache
from dataclasses import dataclass
from fastapi import Request
from typing import Optional, Dict, Any
from urllib.parse import urlparse
from loguru import logger
from persai.errors import ConfigurationError, CredentialsError


@cache
def is_auth_enabled() -> bool:
    """
    Check if authentication is enabled via PERSAI_AUTH environment variable.
    Defaults to True if not set or invalid value.
    """
    auth_setting = os.getenv("PERSAI_AUTH", "true").lower()
    return auth_setting != "false"


@dataclass
class AuthInfo:
    """Encapsulates authentication information for API requests."""

    auth_token: Optional[str]
    refresh_token: Optional[str]
    perses_url: str
    payload: Optional[Dict]

    def auth_token_should_refresh(self, threshold_seconds: int = 60) -> bool:
        """
        Check if auth token is expired or near expiration and should be refreshed.

        :param threshold_seconds: Seconds before expiration to consider token as needing refresh
        :returns: True if token is expired or within threshold of expiration
        """
        if not self.payload or "exp" not in self.payload:
            return True  # Consider invalid tokens as expired

        current_time = int(time.time())
        expiration_time = self.payload["exp"]

        return current_time >= (expiration_time - threshold_seconds)


def parse_jwt_payload(jwt_token: str) -> Dict[str, Any]:
    """
    Parse JWT token and extract payload without verification.
    Note: This is for metadata extraction only, not for security validation.
    """
    if not jwt_token:
        logger.warning("No JWT token provided")
        raise CredentialsError("No JWT token provided")

    # JWT has format: header.payload.signature
    parts = jwt_token.split(".")
    if len(parts) != 3:
        logger.warning("Invalid JWT format - expected 3 parts")
        raise CredentialsError("Invalid JWT format")

    # Decode the payload (second part)
    payload_encoded = parts[1]

    # Add padding if needed for base64 decoding
    padding = 4 - (len(payload_encoded) % 4)
    if padding != 4:
        payload_encoded += "=" * padding

    try:
        payload_bytes = base64.urlsafe_b64decode(payload_encoded)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to decode JWT payload: {e}")
        raise CredentialsError("Failed to decode JWT payload")

    return payload


def resolve_perses_url(request: Request) -> str:
    """
    Resolve the Perses URL from environment variable or request origin.
    """
    perses_url = os.getenv("PERSES_API_URL")

    if not perses_url:
        # Try to derive from origin header
        origin = request.headers.get("origin")
        if origin:
            parsed = urlparse(origin)
            perses_url = f"{parsed.scheme}://{parsed.netloc}"

    if not perses_url:
        raise ConfigurationError(
            "Unable to construct Perses URL. PERSES_API_URL not set and no origin header found"
        )

    return perses_url


class CookieAuthProvider:
    """Extract JWT auth token and refresh token from cookies."""

    @staticmethod
    async def get_auth_info(request: Request) -> AuthInfo:
        """
        Extract complete authentication information from cookies.
        Returns AuthInfo with auth token, refresh token, and resolved Perses URL.
        """
        jwt_payload = request.cookies.get("jwtPayload")
        jwt_signature = request.cookies.get("jwtSignature")
        refresh_token = request.cookies.get("jwtRefreshToken")
        if not jwt_payload or not jwt_signature or not refresh_token:
            raise CredentialsError("JWT cookies not found or incomplete")
        jwt_token = f"{jwt_payload}.{jwt_signature}"

        perses_url = resolve_perses_url(request)
        payload = parse_jwt_payload(jwt_token)

        return AuthInfo(
            auth_token=jwt_token,
            refresh_token=refresh_token,
            perses_url=perses_url,
            payload=payload,
        )
