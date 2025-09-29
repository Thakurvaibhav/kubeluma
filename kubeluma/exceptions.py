"""
Custom exceptions for Kubeluma.

This module defines custom exception classes used throughout the Kubeluma application
to provide more specific error handling and better error messages for different
failure scenarios.

Exception Hierarchy:
- KubelumaError: Base exception for all Kubeluma-specific errors
  - KubernetesConnectionError: Raised when unable to connect to Kubernetes cluster
  - InvalidPatternError: Raised when an invalid regex pattern is provided
  - MetricsUnavailableError: Raised when metrics server is not available
  - PodNotFoundError: Raised when a requested pod is not found
  - ConfigurationError: Raised when there's a configuration issue

Example:
    ```python
    try:
        validate_regex_pattern("invalid[regex")
    except InvalidPatternError as e:
        print(f"Pattern validation failed: {e}")
    ```
"""


class KubelumaError(Exception):
    """Base exception for Kubeluma errors."""
    pass


class KubernetesConnectionError(KubelumaError):
    """Raised when unable to connect to Kubernetes cluster."""
    pass


class InvalidPatternError(KubelumaError):
    """Raised when an invalid regex pattern is provided."""
    pass


class MetricsUnavailableError(KubelumaError):
    """Raised when metrics server is not available."""
    pass


class PodNotFoundError(KubelumaError):
    """Raised when a requested pod is not found."""
    pass


class ConfigurationError(KubelumaError):
    """Raised when there's a configuration issue."""
    pass
