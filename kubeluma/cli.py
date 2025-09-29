"""
Command-line interface for Kubeluma.

This module provides the command-line interface for the Kubeluma application,
handling argument parsing, input validation, and server startup. It supports
various configuration options including pod patterns, namespaces, and server settings.

Key Functions:
- build_parser: Create and configure the argument parser
- main: Main entry point for the CLI application

The CLI supports both interactive mode (where users enter pod patterns in the web UI)
and pre-configured mode (where patterns are provided via command-line arguments).

Example:
    ```bash
    # Interactive mode
    kubeluma serve

    # Pre-configured mode
    kubeluma serve --pod '^api-' --namespace prod --port 8080
    ```
"""

import argparse
import asyncio
import sys
import os
import webbrowser
from .server import run_server
from .validation import validate_regex_pattern, validate_port, validate_host, validate_metrics_interval
from .exceptions import InvalidPatternError, ConfigurationError
from .constants import (
    DEFAULT_HOST, DEFAULT_PORT, DEFAULT_METRICS_INTERVAL_SECONDS,
    BROWSER_OPEN_DELAY_SECONDS
)


def build_parser() -> argparse.ArgumentParser:
    """
    Build and configure the command-line argument parser.
    
    Creates an ArgumentParser with all supported command-line options for Kubeluma,
    including server configuration, Kubernetes connection settings, and pod filtering
    options. Environment variables are used as defaults where appropriate.
    
    Returns:
        argparse.ArgumentParser: Configured argument parser with all options
        
    Environment Variables:
        KUBELUMA_HOST: Default host to bind to (default: localhost)
        KUBELUMA_PORT: Default port to bind to (default: 8080)
        
    Example:
        ```python
        parser = build_parser()
        args = parser.parse_args()
        ```
    """
    env_host = os.getenv('KUBELUMA_HOST', DEFAULT_HOST)
    env_port = int(os.getenv('KUBELUMA_PORT', str(DEFAULT_PORT)))
    
    p = argparse.ArgumentParser("kubeluma", description="Real-time Kubernetes pod inspection UI (multi-pod by regex)")
    p.add_argument("command", choices=['serve'], help="Subcommand to run (only 'serve' supported)")
    p.add_argument("--pod", help="Regex pattern to match pod names (e.g. ^api-) (optional: can be set in UI)")
    p.add_argument("--namespace", default=None, help="Namespace to watch (default: all)")
    p.add_argument("--kubeconfig", default=None, help="Path to kubeconfig (defaults to kube rules)")
    p.add_argument("--context", default=None, help="Kubecontext override")
    p.add_argument("--host", default=env_host, help="Host to bind (env: KUBELUMA_HOST)")
    p.add_argument("--port", type=int, default=env_port, help="Port for HTTP server (env: KUBELUMA_PORT)")
    p.add_argument("--no-open", action="store_true", help="Do not open browser automatically")
    p.add_argument("--metrics-interval", type=float, default=DEFAULT_METRICS_INTERVAL_SECONDS, help="Metrics poll interval seconds")
    return p


def main() -> None:
    """
    Main entry point for the Kubeluma CLI application.
    
    Parses command-line arguments, validates configuration, and starts the Kubeluma
    server. Handles input validation, error reporting, and graceful shutdown on
    interruption.
    
    The function performs the following steps:
    1. Parse command-line arguments
    2. Validate all input parameters
    3. Optionally open browser to the server URL
    4. Start the server with validated configuration
    5. Handle shutdown gracefully
    
    Raises:
        SystemExit: On configuration errors (exit code 2) or server errors (exit code 1)
        
    Example:
        ```bash
        kubeluma serve --pod '^api-' --namespace prod --port 8080
        ```
    """
    parser = build_parser()
    args = parser.parse_args()

    if args.command != 'serve':  # defensive
        parser.error("Only 'serve' supported")

    # Validate inputs
    try:
        pod_regex = None
        if args.pod:
            pod_regex = validate_regex_pattern(args.pod)
        
        host = validate_host(args.host)
        port = validate_port(args.port)
        metrics_interval = validate_metrics_interval(args.metrics_interval)
        
    except (InvalidPatternError, ConfigurationError) as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(2)

    url = f"http://{host}:{port}"
    if not args.no_open:
        asyncio.get_event_loop().call_later(BROWSER_OPEN_DELAY_SECONDS, webbrowser.open, url)

    try:
        asyncio.run(run_server(
            pod_pattern=pod_regex,
            namespace=args.namespace,
            kubeconfig=args.kubeconfig,
            context=args.context,
            port=port,
            metrics_interval=metrics_interval,
            host=host,
        ))
    except KeyboardInterrupt:
        print("\nShutting down...", file=sys.stderr)
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":  # pragma: no cover
    main()
