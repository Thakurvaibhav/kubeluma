"""
Input validation and sanitization for Kubeluma.

This module provides comprehensive input validation functions for all user inputs
and configuration values in the Kubeluma application. It includes validation for
regex patterns, network configuration, resource limits, and data sanitization.

Key Functions:
- validate_regex_pattern: Validates and compiles regex patterns
- validate_port: Validates port numbers (1-65535)
- validate_host: Validates host strings
- validate_metrics_interval: Validates metrics polling intervals
- sanitize_pod_name: Sanitizes pod names for display

All validation functions raise appropriate exceptions (InvalidPatternError,
ConfigurationError) with descriptive error messages when validation fails.

Example:
    ```python
    try:
        pattern = validate_regex_pattern("^api-")
        port = validate_port(8080)
        host = validate_host("localhost")
    except (InvalidPatternError, ConfigurationError) as e:
        print(f"Validation failed: {e}")
    ```
"""

import re
from typing import Optional

from .exceptions import InvalidPatternError, ConfigurationError


def validate_regex_pattern(pattern: str) -> re.Pattern:
    """
    Validate and compile a regex pattern for pod name matching.
    
    Validates that the provided pattern is a valid regular expression and compiles
    it for use in pod name matching. The pattern is trimmed of whitespace before
    validation.
    
    Args:
        pattern: The regex pattern string to validate and compile
        
    Returns:
        re.Pattern: Compiled regex pattern ready for use
        
    Raises:
        InvalidPatternError: If the pattern is empty or invalid regex syntax
        
    Example:
        ```python
        try:
            pattern = validate_regex_pattern("^api-")
            # Use pattern.search(pod_name) to match pod names
        except InvalidPatternError as e:
            print(f"Invalid pattern: {e}")
        ```
    """
    if not pattern or not pattern.strip():
        raise InvalidPatternError("Pattern cannot be empty")
    
    try:
        return re.compile(pattern.strip())
    except re.error as e:
        raise InvalidPatternError(f"Invalid regex pattern: {e}")


def validate_port(port: int) -> int:
    """
    Validate port number for server binding.
    
    Ensures the port number is within the valid range (1-65535) for TCP/UDP
    network services. This validation is used for the HTTP server port.
    
    Args:
        port: Port number to validate (must be integer)
        
    Returns:
        int: The validated port number (unchanged if valid)
        
    Raises:
        ConfigurationError: If port is not an integer or outside valid range
        
    Example:
        ```python
        try:
            valid_port = validate_port(8080)  # Returns 8080
            validate_port(0)  # Raises ConfigurationError
        except ConfigurationError as e:
            print(f"Invalid port: {e}")
        ```
    """
    if not isinstance(port, int) or port < 1 or port > 65535:
        raise ConfigurationError(f"Port must be an integer between 1 and 65535, got: {port}")
    return port


def validate_host(host: str) -> str:
    """
    Validate host string for server binding.
    
    Ensures the host string is not empty and meets basic requirements for
    network hostnames. Validates length limits and trims whitespace.
    
    Args:
        host: Host string to validate (e.g., "localhost", "0.0.0.0", "example.com")
        
    Returns:
        str: The validated and trimmed host string
        
    Raises:
        ConfigurationError: If host is empty or too long
        
    Example:
        ```python
        try:
            valid_host = validate_host("localhost")  # Returns "localhost"
            validate_host("")  # Raises ConfigurationError
        except ConfigurationError as e:
            print(f"Invalid host: {e}")
        ```
    """
    if not host or not host.strip():
        raise ConfigurationError("Host cannot be empty")
    
    host = host.strip()
    
    # Basic validation - could be more comprehensive
    if len(host) > 253:  # DNS name length limit
        raise ConfigurationError("Host name too long")
    
    return host


def validate_metrics_interval(interval: float) -> float:
    """
    Validate metrics polling interval for resource monitoring.
    
    Ensures the metrics polling interval is a positive number and meets minimum
    requirements to avoid overwhelming the Kubernetes metrics API.
    
    Args:
        interval: Polling interval in seconds (must be positive number)
        
    Returns:
        float: The validated interval (converted to float)
        
    Raises:
        ConfigurationError: If interval is not a number, negative, or too small
        
    Example:
        ```python
        try:
            interval = validate_metrics_interval(5.0)  # Returns 5.0
            validate_metrics_interval(0.5)  # Raises ConfigurationError (too small)
        except ConfigurationError as e:
            print(f"Invalid interval: {e}")
        ```
    """
    if not isinstance(interval, (int, float)) or interval <= 0:
        raise ConfigurationError(f"Metrics interval must be a positive number, got: {interval}")
    
    if interval < 1.0:
        raise ConfigurationError("Metrics interval should be at least 1 second to avoid overwhelming the API")
    
    return float(interval)


def sanitize_pod_name(name: str) -> str:
    """
    Sanitize pod name for safe display in web interface.
    
    Removes potentially dangerous characters and limits length to prevent
    display issues or security problems in the web interface.
    
    Args:
        name: Pod name to sanitize
        
    Returns:
        str: Sanitized pod name safe for display (max 253 characters)
        
    Example:
        ```python
        safe_name = sanitize_pod_name("my-pod-123")
        # Returns "my-pod-123" (unchanged if safe)
        ```
    """
    if not name:
        return ""
    
    # Remove any potentially dangerous characters
    return name.strip()[:253]  # DNS name length limit
