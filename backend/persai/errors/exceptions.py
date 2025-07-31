"""Custom exceptions for the PersAI application."""


class PersAIException(Exception):
    """Base exception for internal PersAI errors."""

    pass


class ConfigurationError(PersAIException):
    """Configuration-related errors (missing config, invalid settings)."""

    pass


class PrometheusError(PersAIException):
    """Prometheus API errors (external service failures)."""

    pass


class CredentialsError(PersAIException):
    """Authentication-related errors (missing tokens, invalid JWT format, parsing errors)."""

    pass
