import pytest
import json
import base64
import time
from unittest.mock import Mock
from persai.server.auth import (
    CookieAuthProvider,
    parse_jwt_payload,
    AuthInfo,
    resolve_perses_url,
)
from persai.errors.exceptions import ConfigurationError, CredentialsError
from fastapi import Request


def create_jwt_token(
    header: dict, payload: dict, signature: str = "test_signature"
) -> str:
    """Create a JWT token from header, payload, and signature for testing."""

    def encode_part(data: dict) -> str:
        json_str = json.dumps(data, separators=(",", ":"))
        return base64.urlsafe_b64encode(json_str.encode()).decode().rstrip("=")

    header_encoded = encode_part(header)
    payload_encoded = encode_part(payload)
    return f"{header_encoded}.{payload_encoded}.{signature}"


@pytest.fixture
def sample_jwt_header():
    """Sample JWT header for testing."""
    return {"alg": "HS256", "typ": "JWT"}


@pytest.fixture
def sample_jwt_payload():
    """Sample JWT payload for testing."""
    return {"sub": "1234567890", "name": "John Doe", "iat": 1516239022}


@pytest.fixture
def sample_jwt_token(sample_jwt_header, sample_jwt_payload):
    """Generate a complete JWT token for testing."""
    return create_jwt_token(sample_jwt_header, sample_jwt_payload, "test_signature")


@pytest.fixture
def jwt_cookie_parts(sample_jwt_token):
    """Split JWT token into cookie parts (payload + signature)."""
    parts = sample_jwt_token.split(".")
    return {
        "jwtPayload": f"{parts[0]}.{parts[1]}",  # header.payload
        "jwtSignature": parts[2],  # signature
    }


def test_parse_jwt_payload_valid(sample_jwt_token, sample_jwt_payload):
    """Test parsing a valid JWT token"""
    payload = parse_jwt_payload(sample_jwt_token)

    assert payload == sample_jwt_payload


def test_parse_jwt_payload_custom_data():
    """Test parsing JWT with custom payload data"""
    custom_header = {"alg": "RS256", "typ": "JWT"}
    custom_payload = {
        "sub": "user123",
        "email": "test@example.com",
        "roles": ["admin", "user"],
        "exp": 1700000000,
    }

    jwt_token = create_jwt_token(custom_header, custom_payload)
    parsed_payload = parse_jwt_payload(jwt_token)

    assert parsed_payload is not None
    assert parsed_payload == custom_payload
    assert parsed_payload["sub"] == "user123"
    assert parsed_payload["email"] == "test@example.com"
    assert parsed_payload["roles"] == ["admin", "user"]


def test_parse_jwt_payload_invalid_format():
    """Test parsing JWT with invalid format"""
    jwt_token = "invalid.token"

    with pytest.raises(CredentialsError, match="Invalid JWT format"):
        parse_jwt_payload(jwt_token)


def test_parse_jwt_payload_empty_string():
    """Test parsing empty JWT token"""
    jwt_token = ""

    with pytest.raises(CredentialsError, match="No JWT token provided"):
        parse_jwt_payload(jwt_token)


def test_auth_token_should_refresh_expired():
    """Test auth token should refresh with expired token"""
    # Create a token that expired 1 hour ago
    expired_time = int(time.time()) - 3600
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": "user", "exp": expired_time}
    token = create_jwt_token(header, payload)

    auth_info = AuthInfo(
        auth_token=token,
        refresh_token="refresh-token",
        perses_url="http://perses.example.com",
        payload=payload,
    )

    assert auth_info.auth_token_should_refresh() is True


def test_auth_token_should_refresh_near_expiry():
    """Test auth token should refresh with token near expiry"""
    # Create a token that expires in 30 seconds (within 60s threshold)
    near_expiry_time = int(time.time()) + 30
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": "user", "exp": near_expiry_time}
    token = create_jwt_token(header, payload)

    auth_info = AuthInfo(
        auth_token=token,
        refresh_token="refresh-token",
        perses_url="http://perses.example.com",
        payload=payload,
    )

    assert auth_info.auth_token_should_refresh(60) is True


def test_auth_token_should_refresh_valid():
    """Test auth token should refresh with valid token"""
    # Create a token that expires in 2 hours
    future_time = int(time.time()) + 7200
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": "user", "exp": future_time}
    token = create_jwt_token(header, payload)

    auth_info = AuthInfo(
        auth_token=token,
        refresh_token="refresh-token",
        perses_url="http://perses.example.com",
        payload=payload,
    )

    assert auth_info.auth_token_should_refresh(60) is False


def test_auth_token_should_refresh_invalid_token():
    """Test auth token should refresh with invalid token"""
    auth_info = AuthInfo(
        auth_token="invalid-token",
        refresh_token="refresh-token",
        perses_url="http://perses.example.com",
        payload={},
    )

    assert auth_info.auth_token_should_refresh() is True


def test_resolve_perses_url_from_env(monkeypatch):
    """Test resolving Perses URL from environment variable"""
    monkeypatch.setenv("PERSES_API_URL", "http://perses-env.example.com")

    request = Mock(spec=Request)
    request.headers = {}

    url = resolve_perses_url(request)
    assert url == "http://perses-env.example.com"


def test_resolve_perses_url_from_origin():
    """Test resolving Perses URL from origin header"""
    request = Mock(spec=Request)
    request.headers = {"origin": "http://perses-origin.example.com"}

    url = resolve_perses_url(request)
    assert url == "http://perses-origin.example.com"


def test_resolve_perses_url_no_source():
    """Test resolving Perses URL with no source fails"""
    request = Mock(spec=Request)
    request.headers = {}

    with pytest.raises(ConfigurationError, match="Unable to construct Perses URL"):
        resolve_perses_url(request)


@pytest.mark.asyncio
async def test_get_auth_info_success(
    jwt_cookie_parts, sample_jwt_token, sample_jwt_header, monkeypatch
):
    """Test CookieAuthProvider.get_auth_info with valid cookies"""
    monkeypatch.setenv("PERSES_API_URL", "http://perses.example.com")

    # Create a valid refresh token
    refresh_payload = {"sub": "1234567890", "exp": int(time.time()) + 7200}
    refresh_token = create_jwt_token(
        sample_jwt_header, refresh_payload, "refresh_signature"
    )

    request = Mock(spec=Request)
    request.cookies = {**jwt_cookie_parts, "jwtRefreshToken": refresh_token}
    request.headers = {}

    provider = CookieAuthProvider()
    auth_info = await provider.get_auth_info(request)

    assert auth_info is not None
    assert auth_info.auth_token == sample_jwt_token
    assert auth_info.refresh_token == refresh_token
    assert auth_info.perses_url == "http://perses.example.com"
    assert auth_info.payload is not None


@pytest.mark.asyncio
async def test_get_auth_info_no_jwt_token():
    """Test CookieAuthProvider.get_auth_info with no JWT token"""
    request = Mock(spec=Request)
    request.cookies = {}
    request.headers = {}

    provider = CookieAuthProvider()

    with pytest.raises(CredentialsError, match="JWT cookies not found"):
        await provider.get_auth_info(request)


@pytest.mark.asyncio
async def test_get_auth_info_no_perses_url(jwt_cookie_parts, sample_jwt_header):
    """Test CookieAuthProvider.get_auth_info with no Perses URL source"""
    # Create a valid refresh token
    refresh_payload = {"sub": "1234567890", "exp": int(time.time()) + 7200}
    refresh_token = create_jwt_token(
        sample_jwt_header, refresh_payload, "refresh_signature"
    )

    request = Mock(spec=Request)
    request.cookies = {**jwt_cookie_parts, "jwtRefreshToken": refresh_token}
    request.headers = {}

    provider = CookieAuthProvider()

    with pytest.raises(ConfigurationError, match="Unable to construct Perses URL"):
        await provider.get_auth_info(request)
