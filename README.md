# Kubeluma

Real-time, zero-dependency (frontend) Kubernetes pod inspection UI.

Current focus: fast multi‑pod debugging via regex + live logs, events, metrics, env vars with resource request/limit awareness.

## Key Features
- Start with: `kubeluma serve` (no arguments) → browser opens → enter a pod name regex interactively.
- Optional CLI `--pod` regex to pre-seed pattern (skips overlay).
- Regex multi-match: table of all matching pods (sortable by name) incl. namespace, phase, readiness, restarts.
- Auto-refresh pod discovery (interval configurable via `KUBELUMA_POD_REFRESH_SEC`).
- Focus a pod (row click) to stream:
  * Live container logs (per-container subscription; pause/resume follow)
  * Pod + container status (ready, restarts, phase, IPs, node)
  * Resource metrics with % of request & % of limit (CPU m, Mem MiB) if metrics-server present
  * Threshold highlighting (env: `KUBELUMA_CPU_LIMIT_RED_PCT`, `KUBELUMA_MEM_LIMIT_RED_PCT`)
  * Kubernetes events (pod-scoped, filtered per focused pod; age in s/m/h/d)
  * Environment variables per container (value or source; secrets masked as `*** (secret name/key)`).
- Pattern badge + “New Search” button to reset / change regex without restart.
- Namespace column + Pod IP & Node IP in status panel.
- Fast refresh trigger on pattern changes (no full wait cycle).

## Recent Enhancements
- Percentage metrics vs requests & limits.
- Configurable red highlight thresholds via env vars.
- Pod events filtered client-side per focused pod with "No events" placeholder.
- Auto pod list refresh detects new & removed pods.
- Improved logging (focus changes, metrics timing, events cycle summaries).

## CLI
```
# Interactive (regex entered in UI)
kubeluma serve

# Pre-supplied regex
kubeluma serve --pod '^api-'

# Restrict to a namespace
kubeluma serve --pod '^web-' --namespace prod

# With explicit kube context
kubeluma serve --pod mypod --kubeconfig ~/.kube/config --context staging
```

### Flags
| Flag | Description |
|------|-------------|
| serve | Subcommand (required) |
| --pod | Optional pod name regex (otherwise set in UI) |
| --namespace | Namespace filter (omit = all namespaces) |
| --kubeconfig | Path to kubeconfig (defaults to standard loading) |
| --context | Kube context override |
| --host | Bind host (env: KUBELUMA_HOST; default localhost) |
| --port | Port (env: KUBELUMA_PORT; default 8080) |
| --no-open | Do not auto-launch browser |
| --metrics-interval | Metrics poll interval seconds (default 5) |

### Relevant Environment Vars
| Var | Purpose | Default |
|-----|---------|---------|
| KUBELUMA_CPU_LIMIT_RED_PCT | CPU % of limit highlight threshold | 90 |
| KUBELUMA_MEM_LIMIT_RED_PCT | Memory % of limit highlight threshold | 80 |
| KUBELUMA_POD_REFRESH_SEC | Pod list refresh interval | 5 |
| KUBELUMA_LOG_LEVEL | App log level | INFO |
| KUBELUMA_UVICORN_LEVEL | Uvicorn log level | info |

## HTTP Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | / | UI (single page) |
| POST | /api/set_pattern | Body `{ "pattern": "^api-" }` sets regex & triggers immediate refresh |
| POST | /api/reset_pattern | Clears pattern & prompts UI overlay |
| GET | /api/current_pattern | Returns `{ pattern: str | null }` |
| WS | /ws | Bi-directional event/data stream |

## WebSocket Flow
Client → Server:
```jsonc
{"action":"subscribe","channel":"pod"}
{"action":"subscribe","channel":"logs","pod":"pod-a","container":"app"}
{"action":"focus","pod":"pod-b"}
```
Server → Client types:
```jsonc
{"type":"awaitingPattern"}
{"type":"pods","data":{"pods":[{"name":"pod-a","namespace":"default","phase":"Running","restarts":0,"ready":1,"total":1}],"focus":"pod-a","pattern":"^api-"}}
{"type":"pod","data":{ /* full focused pod view */ }}
{"type":"log","pod":"pod-a","container":"app","line":"..."}
{"type":"event","data":{ "pod":"pod-a","type":"Warning","reason":"BackOff","message":"...","ageSeconds":120 }}
{"type":"metrics","data":{"containers":[{"name":"app","cpu":12,"memoryMiB":34.5,"cpuPctOfLimit":30.0}]}}
```

### Focused Pod View Shape
```jsonc
{
  "name": "pod-a",
  "namespace": "default",
  "phase": "Running",
  "node": "10.0.0.12",
  "podIP": "10.244.1.23",
  "ageSeconds": 845,
  "containers": [
    {
      "name": "app",
      "ready": true,
      "restarts": 1,
      "state": "running",
      "image": "repo/app:1.2.3",
      "resources": { "requests": {"cpu":"100m","memory":"128Mi"}, "limits": {"cpu":"200m","memory":"256Mi"} },
      "env": [ {"name":"ENV_MODE","value":"prod"}, {"name":"SECRET_TOKEN","value":"*** (secret mysecret/token)"} ]
    }
  ]
}
```

## Metrics Notes
- CPU normalized to millicores (m); memory to MiB.
- Percent columns omitted if request/limit not defined for that resource.
- `disabled` flag broadcast if metrics API unavailable.

## Refresh Strategy
- Pods: every `KUBELUMA_POD_REFRESH_SEC` or instant on pattern change.
- Events: every ~6s with events.k8s.io → core fallback; client filters to focused pod.
- Metrics: focused pod only at `--metrics-interval` seconds.
- Logs: per-container streaming only after subscription to reduce load.

## Running via Docker
```
# Build image
docker build -t kubeluma:local .

# Run (interactive pattern entry)
docker run --rm -p 8080:8080 -v ~/.kube:/home/kubeluma/.kube:ro \
  -e KUBECONFIG=/home/kubeluma/.kube/config kubeluma:local

# Pre-supply regex & namespace
docker run --rm -p 8080:8080 -v ~/.kube:/home/kubeluma/.kube:ro \
  kubeluma:local kubeluma serve --pod '^api-' --namespace prod
```

## Development
```
python -m venv .venv
source .venv/bin/activate
pip install -e .

kubeluma serve            # interactive pattern
kubeluma serve --pod mypod # immediate pattern
```

## Roadmap Ideas
- Multi-pod focused metrics aggregate view
- Sort by highest CPU / memory
- Download logs button
- Pod describe dump panel
- RBAC error surfacing for events/metrics

## License
Internal / TBD.
