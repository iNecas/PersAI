import time
import json
import base64
from unittest.mock import Mock, patch, MagicMock
import pytest

from persai.server.token_validator import TokenValidator, ValidationResult
from persai.server.auth import AuthInfo
from persai.errors.exceptions import CredentialsError


class TestTokenValidator:
    """Test cases for TokenValidator class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = TokenValidator()
        
        # Create a mock AuthInfo
        self.mock_payload = {
            "sub": "test-user",
            "exp": int(time.time()) + 3600,  # 1 hour from now
        }
        
        # Create a mock refresh token
        refresh_payload = {
            "sub": "test-user", 
            "exp": int(time.time()) + 7200,  # 2 hours from now
        }
        self.mock_refresh_token = self._create_mock_jwt(refresh_payload)
        
        self.mock_auth_info = AuthInfo(
            auth_token="mock.jwt.token",
            refresh_token=self.mock_refresh_token,
            perses_url="https://perses.example.com",
            payload=self.mock_payload,
        )

    def _create_mock_jwt(self, payload):
        """Create a mock JWT token for testing."""
        header = {"alg": "HS256", "typ": "JWT"}
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        signature = "mock_signature"
        return f"{header_b64}.{payload_b64}.{signature}"

    def test_get_refresh_token_cache_key(self):
        """Test cache key generation from refresh token."""
        cache_key = self.validator._get_refresh_token_cache_key("test_token")
        assert isinstance(cache_key, str)
        assert len(cache_key) == 64  # SHA256 hex digest length
        
        # Same token should produce same key
        cache_key2 = self.validator._get_refresh_token_cache_key("test_token")
        assert cache_key == cache_key2
        
        # Different tokens should produce different keys
        cache_key3 = self.validator._get_refresh_token_cache_key("different_token")
        assert cache_key != cache_key3


    def test_is_cache_valid_no_cache(self):
        """Test cache validity when no cache entry exists."""
        cache_key = "nonexistent_key"
        result = self.validator._is_cache_valid(cache_key)
        assert result is False

    def test_is_cache_valid_expired_validation(self):
        """Test cache validity when validation has expired."""
        cache_key = "test_key"
        
        # Create an expired cache entry (older than 3600 seconds)
        self.validator._validation_cache[cache_key] = ValidationResult(
            is_valid=True,
            validated_at=time.time() - 4000  # Over 1 hour ago
        )
        
        result = self.validator._is_cache_valid(cache_key)
        assert result is False

    def test_is_cache_valid_within_duration(self):
        """Test cache validity when within cache duration."""
        cache_key = "test_key"
        
        # Create a recent cache entry
        self.validator._validation_cache[cache_key] = ValidationResult(
            is_valid=True,
            validated_at=time.time() - 60  # 1 minute ago
        )
        
        result = self.validator._is_cache_valid(cache_key)
        assert result is True

    @patch('persai.agent.tools.PrometheusClient._refresh_token')
    def test_validate_via_refresh_success(self, mock_refresh_token):
        """Test successful validation via refresh."""
        # Mock successful refresh token call
        mock_updated_auth = AuthInfo(
            auth_token=self._create_mock_jwt({"sub": "test-user", "exp": int(time.time()) + 3600}),
            refresh_token=self.mock_refresh_token,
            perses_url="https://perses.example.com",
            payload={"sub": "test-user", "exp": int(time.time()) + 3600}
        )
        mock_refresh_token.return_value = mock_updated_auth

        result = self.validator._validate_via_refresh(self.mock_auth_info)
        
        assert result.is_valid is True
        assert result.error is None
        assert result.validated_at is not None
        assert result.expires_at is not None

        # Verify the refresh method was called
        mock_refresh_token.assert_called_once()

    @patch('persai.agent.tools.PrometheusClient._refresh_token')
    def test_validate_via_refresh_failure(self, mock_refresh_token):
        """Test failed validation via refresh."""
        # Mock the _refresh_token method to raise an exception (simulating failure)
        mock_refresh_token.side_effect = Exception("Refresh failed with status 401")

        result = self.validator._validate_via_refresh(self.mock_auth_info)
        
        assert result.is_valid is False
        assert result.error is not None
        assert "Refresh failed with status 401" in result.error

    def test_validate_via_refresh_no_refresh_token(self):
        """Test validation when no refresh token is available."""
        auth_info_no_refresh = AuthInfo(
            auth_token="mock.jwt.token",
            refresh_token=None,
            perses_url="https://perses.example.com",
            payload=self.mock_payload
        )

        result = self.validator._validate_via_refresh(auth_info_no_refresh)
        
        assert result.is_valid is False
        assert "No refresh token" in result.error

    @patch('persai.agent.tools.PrometheusClient._refresh_token')
    def test_validate_via_refresh_exception(self, mock_refresh_token):
        """Test validation when request raises exception."""
        mock_refresh_token.side_effect = Exception("Network error")

        result = self.validator._validate_via_refresh(self.mock_auth_info)
        
        assert result.is_valid is False
        assert "Network error" in result.error

    @patch.object(TokenValidator, '_validate_via_refresh')
    def test_validate_auth_info_cache_hit(self, mock_validate):
        """Test validation with cache hit."""
        # Pre-populate cache
        cache_key = self.validator._get_refresh_token_cache_key(self.mock_refresh_token)
        cached_result = ValidationResult(
            is_valid=True,
            validated_at=time.time() - 60
        )
        self.validator._validation_cache[cache_key] = cached_result

        result = self.validator.validate_auth_info(self.mock_auth_info)
        
        assert result == cached_result
        mock_validate.assert_not_called()

    @patch.object(TokenValidator, '_validate_via_refresh')
    def test_validate_auth_info_cache_miss(self, mock_validate):
        """Test validation with cache miss."""
        mock_result = ValidationResult(is_valid=True, validated_at=time.time())
        mock_validate.return_value = mock_result

        result = self.validator.validate_auth_info(self.mock_auth_info)
        
        assert result == mock_result
        mock_validate.assert_called_once_with(self.mock_auth_info)
        
        # Check that result was cached
        cache_key = self.validator._get_refresh_token_cache_key(self.mock_refresh_token)
        assert cache_key in self.validator._validation_cache
        assert self.validator._validation_cache[cache_key] == mock_result

    def test_validate_auth_info_no_refresh_token(self):
        """Test validation when AuthInfo has no refresh token."""
        auth_info_no_refresh = AuthInfo(
            auth_token="mock.jwt.token",
            refresh_token=None,
            perses_url="https://perses.example.com",
            payload=self.mock_payload
        )

        result = self.validator.validate_auth_info(auth_info_no_refresh)
        
        assert result.is_valid is False
        assert "No refresh token" in result.error

    def test_cleanup_expired_cache(self):
        """Test cleanup of expired cache entries."""
        # Add some entries - one old, one recent
        old_result = ValidationResult(is_valid=True, validated_at=time.time() - 4000)  # Old
        recent_result = ValidationResult(is_valid=True, validated_at=time.time() - 60)  # Recent
        
        self.validator._validation_cache["old_key"] = old_result
        self.validator._validation_cache["recent_key"] = recent_result
        
        self.validator._cleanup_expired_cache()
        
        # Old entry should be removed, recent should remain
        assert "old_key" not in self.validator._validation_cache
        assert "recent_key" in self.validator._validation_cache


class TestValidationResult:
    """Test cases for ValidationResult dataclass."""

    def test_validation_result_creation(self):
        """Test creating ValidationResult instances."""
        result = ValidationResult(is_valid=True, validated_at=time.time())
        assert result.is_valid is True
        assert result.validated_at is not None
        assert result.expires_at is None
        assert result.error is None

    def test_validation_result_with_error(self):
        """Test ValidationResult with error information."""
        error_msg = "Token expired"
        result = ValidationResult(
            is_valid=False, 
            validated_at=time.time(), 
            error=error_msg
        )
        assert result.is_valid is False
        assert result.error == error_msg