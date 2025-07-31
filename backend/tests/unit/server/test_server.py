import pytest
from ..conftest import create_async_client


class TestCORSConfiguration:
    """Test CORS configuration with different environment variable values by examining HTTP headers."""

    @pytest.mark.asyncio
    async def test_cors_default_origin(self):
        """Test CORS uses default origin when PERSAI_CORS_ORIGINS is not set."""
        async with create_async_client() as client:
            response = await client.options(
                "/",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )

            assert (
                response.headers.get("access-control-allow-origin")
                == "http://localhost:3000"
            )
            assert response.headers.get("access-control-allow-credentials") == "true"
            assert "access-control-allow-methods" in response.headers

    @pytest.mark.asyncio
    async def test_cors_default_origin_rejected(self):
        """Test CORS rejects non-default origin when PERSAI_CORS_ORIGINS is not set."""
        async with create_async_client() as client:
            response = await client.options(
                "/",
                headers={
                    "Origin": "https://example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )

            assert "access-control-allow-origin" not in response.headers

    @pytest.mark.asyncio
    async def test_cors_single_origin(
        self,
    ):
        """Test CORS with single origin from environment variable."""
        test_origin = "https://example.com"
        env_vars = {"PERSAI_CORS_ORIGINS": test_origin}

        async with create_async_client(env_vars) as client:
            response = await client.options(
                "/",
                headers={"Origin": test_origin, "Access-Control-Request-Method": "GET"},
            )

            assert response.headers.get("access-control-allow-origin") == test_origin
            assert response.headers.get("access-control-allow-credentials") == "true"

    @pytest.mark.asyncio
    async def test_cors_single_origin_rejected(
        self,
    ):
        """Test CORS rejects other origins when single origin is configured."""
        test_origin = "https://example.com"
        env_vars = {"PERSAI_CORS_ORIGINS": test_origin}

        async with create_async_client(env_vars) as client:
            response = await client.options(
                "/",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )

            assert "access-control-allow-origin" not in response.headers

    @pytest.mark.asyncio
    async def test_cors_multiple_origins(
        self,
    ):
        """Test CORS with multiple origins from environment variable."""
        test_origins = (
            # Additional artificial whitespace to cover the trimming functionality
            "https://example.com  ,http://localhost:3000, https://app.example.com"
        )
        env_vars = {"PERSAI_CORS_ORIGINS": test_origins}

        async with create_async_client(env_vars) as client:
            # Test first origin
            response1 = await client.options(
                "/",
                headers={
                    "Origin": "https://example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert (
                response1.headers.get("access-control-allow-origin")
                == "https://example.com"
            )

            # Test second origin
            response2 = await client.options(
                "/",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert (
                response2.headers.get("access-control-allow-origin")
                == "http://localhost:3000"
            )

            # Test third origin
            response3 = await client.options(
                "/",
                headers={
                    "Origin": "https://app.example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert (
                response3.headers.get("access-control-allow-origin")
                == "https://app.example.com"
            )

    @pytest.mark.asyncio
    async def test_cors_disabled_when_empty_string(
        self,
    ):
        """Test CORS is disabled when environment variable is empty string."""
        env_vars = {"PERSAI_CORS_ORIGINS": ""}

        async with create_async_client(env_vars) as client:
            response = await client.options(
                "/",
                headers={
                    "Origin": "https://example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )

            # No CORS headers should be present when CORS is disabled
            assert "access-control-allow-origin" not in response.headers
            assert "access-control-allow-credentials" not in response.headers
            assert "access-control-allow-methods" not in response.headers
            assert "access-control-allow-headers" not in response.headers

    @pytest.mark.asyncio
    async def test_cors_credentials(
        self,
    ):
        """Test that CORS includes credentials and other required headers."""
        test_origin = "https://example.com"
        env_vars = {"PERSAI_CORS_ORIGINS": test_origin}

        async with create_async_client(env_vars) as client:
            response = await client.options(
                "/",
                headers={
                    "Origin": test_origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "Content-Type",
                },
            )

            assert response.headers.get("access-control-allow-credentials") == "true"

    @pytest.mark.asyncio
    async def test_cors_rejected_origin_no_origin_header(
        self,
    ):
        """Test that rejected origins don't get the access-control-allow-origin header."""
        test_origin = "https://example.com"
        env_vars = {"PERSAI_CORS_ORIGINS": test_origin}

        async with create_async_client(env_vars) as client:
            response = await client.options(
                "/",
                headers={
                    "Origin": "https://malicious.com",
                    "Access-Control-Request-Method": "GET",
                },
            )

            # The key test is that the rejected origin doesn't get the allow-origin header
            assert "access-control-allow-origin" not in response.headers
            # Other CORS headers may still be present as they're not origin-specific
