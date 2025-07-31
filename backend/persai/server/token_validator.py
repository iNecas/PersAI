import time
import hashlib
from typing import Optional, Dict
from dataclasses import dataclass
from fastapi import Request
from loguru import logger

from .auth import AuthInfo, CookieAuthProvider
from persai.errors import CredentialsError
from persai.agent import PrometheusClient

# The TokenValidator is separate from the rest of auth.py code, as it needs
# to use PrometeusClient, which uses auth.py. If it would be in auth.py,
# it would cause a cyclic dependency.

# Cache validation threshold - how long to consider a validation result valid (1 hour)
VALIDATION_CACHE_TTL_SECONDS = 3600


@dataclass
class ValidationResult:
    """Result of token validation attempt."""

    is_valid: bool
    validated_at: float
    expires_at: Optional[float] = None
    error: Optional[str] = None


class TokenValidator:
    """
    Validates JWT tokens by using refresh token to verify session validity.
    Caches validation results based on refresh token with TTL derived from refresh token expiry.
    """

    def __init__(self):
        self._validation_cache: Dict[str, ValidationResult] = {}

    def _get_refresh_token_cache_key(self, refresh_token: str) -> str:
        """Generate cache key from refresh token hash."""
        return hashlib.sha256(refresh_token.encode()).hexdigest()

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached validation result is still valid based on validation timestamp."""
        if cache_key not in self._validation_cache:
            return False

        cached_result = self._validation_cache[cache_key]
        current_time = time.time()

        # Check if the cached validation is still within the TTL
        return (
            current_time - cached_result.validated_at
        ) < VALIDATION_CACHE_TTL_SECONDS

    def _validate_via_refresh(self, auth_info: AuthInfo) -> ValidationResult:
        """
        Validate session by attempting to use refresh token.
        This doesn't necessarily refresh the access token, just validates the session.
        """
        if not auth_info.refresh_token:
            return ValidationResult(
                is_valid=False,
                validated_at=time.time(),
                error="No refresh token available",
            )

        try:
            logger.debug(
                "Validating session via refresh token", perses_url=auth_info.perses_url
            )

            # Create a PrometheusClient pointing to Perses auth endpoint
            # We use the refresh logic already implemented in PrometheusClient
            client = PrometheusClient(f"{auth_info.perses_url}/api/auth", auth_info)

            # Use the existing _refresh_token method from PrometheusClient
            updated_auth = client._refresh_token()

            return ValidationResult(
                is_valid=True,
                validated_at=time.time(),
                expires_at=updated_auth.payload.get("exp"),
            )

        except Exception as e:
            logger.debug("Session validation failed via refresh", error=str(e))
            return ValidationResult(
                is_valid=False,
                validated_at=time.time(),
                error=f"Validation request failed: {str(e)}",
            )

    def validate_auth_info(self, auth_info: AuthInfo) -> ValidationResult:
        """
        Validate AuthInfo by checking refresh token validity.
        Uses cache based on refresh token to minimize validation requests.
        """
        logger.info("Validating token", user_id=auth_info.payload.get("sub", "unknown"))
        self._cleanup_expired_cache()

        if not auth_info.refresh_token:
            return ValidationResult(
                is_valid=False,
                validated_at=time.time(),
                error="No refresh token provided",
            )

        cache_key = self._get_refresh_token_cache_key(auth_info.refresh_token)
        if self._is_cache_valid(cache_key):
            cached_result = self._validation_cache[cache_key]
            logger.debug("Using cached validation result", cache_key=cache_key[:8])
            return cached_result

        # Cache miss: try to validate via refresh.
        logger.debug(
            "Cache miss - performing session validation", cache_key=cache_key[:8]
        )
        result = self._validate_via_refresh(auth_info)

        self._validation_cache[cache_key] = result
        return result

    def _cleanup_expired_cache(self):
        """Remove old entries from cache to prevent memory leaks."""
        current_time = time.time()
        expired_keys = [
            key
            for key, result in self._validation_cache.items()
            if (current_time - result.validated_at) > VALIDATION_CACHE_TTL_SECONDS
        ]

        for key in expired_keys:
            del self._validation_cache[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} old cache entries")


# Global instance
_token_validator = TokenValidator()


def get_token_validator() -> TokenValidator:
    """Get the global token validator instance."""
    return _token_validator


async def get_validated_auth_info(request: Request) -> AuthInfo:
    """
    FastAPI dependency that returns validated AuthInfo.
    Validates the session using refresh token and caches the result internally in TokenValidator.
    """
    auth_info = await CookieAuthProvider.get_auth_info(request)
    validation_result = get_token_validator().validate_auth_info(auth_info)

    if not validation_result.is_valid:
        raise CredentialsError(f"Token validation failed: {validation_result.error}")

    logger.info("Token validation successful")
    return auth_info
