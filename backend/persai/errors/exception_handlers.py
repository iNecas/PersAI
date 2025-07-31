from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, HTTPException
from llama_stack_client import APIConnectionError
from loguru import logger

from .exceptions import ConfigurationError, PrometheusError, CredentialsError


async def configuration_error_handler(
    request: Request, exc: ConfigurationError
) -> JSONResponse:
    """Handle configuration errors (500 - internal server errors)"""
    logger.exception("Configuration error occurred", error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"type": "ConfigurationError", "message": str(exc)}},
    )


async def prometheus_error_handler(
    request: Request, exc: PrometheusError
) -> JSONResponse:
    """Handle Prometheus API errors (502 - bad gateway)"""
    logger.exception("Prometheus API error", error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"error": {"type": "PrometheusError", "message": str(exc)}},
    )


async def credentials_error_handler(
    request: Request, exc: CredentialsError
) -> JSONResponse:
    """Handle authentication errors (401 - unauthorized)"""
    logger.warning("Authentication error", error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"error": {"type": "CredentialsError", "message": str(exc)}},
    )


async def api_connection_error_handler(
    request: Request, exc: APIConnectionError
) -> JSONResponse:
    """Handle Llama Stack connection errors (503 - service unavailable)"""
    logger.exception("LlamaStack connection failed", error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": {
                "type": "LlamaStackConnectionError",
                "message": "Unable to connect to Llama Stack",
                "detail": str(exc),
            }
        },
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Override default validation error format for consistency"""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "type": "ValidationError",
                "message": "Request validation failed",
                "detail": exc.errors(),
            }
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTPException with consistent error format"""
    logger.warning(
        "HTTP exception occurred", status_code=exc.status_code, detail=exc.detail
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "type": "HTTPException",
                "message": exc.detail,
                "status_code": exc.status_code,
            }
        },
    )


async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Handle generic ValueError exceptions (400 - bad request)"""
    logger.warning("ValueError occurred", error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": {"type": "ValueError", "message": str(exc)}},
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.warning("Generic error", error=str(exc))
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "response": "Internal Error",
            "cause": str(exc),
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers with the FastAPI app."""
    app.add_exception_handler(ConfigurationError, configuration_error_handler)
    app.add_exception_handler(PrometheusError, prometheus_error_handler)
    app.add_exception_handler(CredentialsError, credentials_error_handler)
    app.add_exception_handler(APIConnectionError, api_connection_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValueError, value_error_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
