from .dependencies import argparse, asyncio, webbrowser, re, sys, os
from .server import run_server


def build_parser():
    env_host = os.getenv('KUBELUMA_HOST', 'localhost')
    env_port = int(os.getenv('KUBELUMA_PORT', '8080'))
    p = argparse.ArgumentParser("kubeluma", description="Real-time Kubernetes pod inspection UI (multi-pod by regex)")
    p.add_argument("command", choices=['serve'], help="Subcommand to run (only 'serve' supported)")
    p.add_argument("--pod", help="Regex pattern to match pod names (e.g. ^api-) (optional: can be set in UI)")
    p.add_argument("--namespace", default=None, help="Namespace to watch (default: all)")
    p.add_argument("--kubeconfig", default=None, help="Path to kubeconfig (defaults to kube rules)")
    p.add_argument("--context", default=None, help="Kubecontext override")
    p.add_argument("--host", default=env_host, help="Host to bind (env: KUBELUMA_HOST)")
    p.add_argument("--port", type=int, default=env_port, help="Port for HTTP server (env: KUBELUMA_PORT)")
    p.add_argument("--no-open", action="store_true", help="Do not open browser automatically")
    p.add_argument("--metrics-interval", type=float, default=5.0, help="Metrics poll interval seconds")
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command != 'serve':  # defensive
        parser.error("Only 'serve' supported")

    pod_regex = None
    if args.pod:
        try:
            pod_regex = re.compile(args.pod)
        except re.error as e:
            print(f"Invalid regex pattern: {e}", file=sys.stderr)
            sys.exit(2)

    url = f"http://{args.host}:{args.port}"
    if not args.no_open:
        asyncio.get_event_loop().call_later(1.0, webbrowser.open, url)

    try:
        asyncio.run(run_server(
            pod_pattern=pod_regex,
            namespace=args.namespace,
            kubeconfig=args.kubeconfig,
            context=args.context,
            port=args.port,
            metrics_interval=args.metrics_interval,
            host=args.host,
        ))
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":  # pragma: no cover
    main()
