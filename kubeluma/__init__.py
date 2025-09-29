"""
Kubeluma - Real-time Kubernetes Pod Inspection Tool.

Kubeluma provides a web-based UI for real-time monitoring and debugging of Kubernetes pods
using regex patterns. It offers live log streaming, resource metrics, event monitoring,
and environment variable inspection with a zero-dependency frontend.

Key Features:
- Real-time pod discovery with regex filtering
- Live container log streaming
- Resource metrics with percentage calculations vs requests/limits
- Kubernetes events monitoring
- Environment variable inspection
- Configurable resource alert thresholds
- WebSocket-based real-time updates

Example:
    Basic usage:
    ```bash
    kubeluma serve
    ```

    With pre-configured pod pattern:
    ```bash
    kubeluma serve --pod '^api-'
    ```

    In a specific namespace:
    ```bash
    kubeluma serve --pod '^web-' --namespace prod
    ```
"""

__all__ = ["__version__"]
__version__ = "0.0.1"
