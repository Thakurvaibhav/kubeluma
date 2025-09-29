"""
Constants and configuration for Kubeluma.

This module contains all the configuration constants used throughout the Kubeluma
application, including polling intervals, resource thresholds, memory limits, and
default values for various settings.

Constants are organized by category:
- Event tracking: Limits and timeouts for event processing
- Polling intervals: Default intervals for various background tasks
- Resource thresholds: CPU and memory alert thresholds
- Client limits: Browser-side data limits
- WebSocket settings: Connection and broadcast timeouts
- Logging: Default log levels
- Server defaults: Default host and port configurations
- Kubernetes API: API group and version constants
- Container user: User configuration for Docker containers
"""

# Event tracking constants
SEEN_EVENTS_MAX = 5000
SEEN_EVENTS_TTL_SECONDS = 3600  # 1 hour

# Polling intervals (in seconds)
DEFAULT_POD_REFRESH_SECONDS = 5
DEFAULT_METRICS_INTERVAL_SECONDS = 5.0
DEFAULT_EVENTS_POLL_INTERVAL_SECONDS = 6
DEFAULT_LOG_STREAM_CHECK_INTERVAL_SECONDS = 2

# Resource threshold percentages
DEFAULT_CPU_LIMIT_RED_PERCENT = 90
DEFAULT_MEM_LIMIT_RED_PERCENT = 80

# Client-side limits
MAX_EVENTS_HISTORY = 3000
MAX_RECENT_EVENTS_DISPLAY = 300

# WebSocket and connection management
WEBSOCKET_BROADCAST_TIMEOUT = 1.0
BROWSER_OPEN_DELAY_SECONDS = 1.0

# Logging
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_UVICORN_LOG_LEVEL = "info"

# Server defaults
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8080
DEFAULT_DOCKER_PORT = 8080
DEFAULT_DOCKER_HOST = "0.0.0.0"

# Kubernetes API
METRICS_API_GROUP = "metrics.k8s.io"
METRICS_API_VERSION = "v1beta1"
METRICS_API_PLURAL = "pods"

# Container user
KUBELUMA_USER_ID = 10001
KUBELUMA_USER_HOME = "/home/kubeluma"
