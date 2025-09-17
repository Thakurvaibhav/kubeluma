# Kubeluma

Real-time, zero-dependency (frontend) Kubernetes pod inspection UI.

Current focus: fast multi‑pod debugging via regex + live logs, events, metrics, env vars.

## Key Features
- Start with: `kubeluma serve` (no arguments) → browser opens → enter a pod name regex interactively.
- Optional CLI `--pod` regex to pre-seed pattern (skips overlay).
- Regex multi-match: table of all matching pods (sortable by name) incl. namespace, phase, readiness, restarts.
- Focus a pod (row click) to stream:
  * Live container logs (per-container subscription; pause/resume follow)
  * Pod + container status (ready, restarts, phase)
  * Basic resource metrics (CPU m, Memory MiB) if metrics-server present
  * Kubernetes events (pod-scoped, rolling feed, age in minutes)
  * Environment variables per container (value or source; secrets masked as `*** (secret name/key)`).
- Pattern badge + “New Search” button to reset / change regex without restarting server.
- Namespace column + Pod IP & Node IP in status panel.
- Fast refresh trigger on pattern changes (no 5s wait).

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

## HTTP Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | / | UI (static single page) |
| POST | /api/set_pattern | Body `{"pattern": "^api-"}` sets regex & triggers immediate refresh |
| POST | /api/reset_pattern | Clears pattern & prompts UI overlay |
| GET | /api/current_pattern | Returns `{ pattern: str | null }` |
| WS | /ws | Bi-directional event / data stream |

## WebSocket Flow
Client → Server:
```jsonc
{"action":"subscribe","channel":"pod"}
{"action":"subscribe","channel":"logs","pod":"pod-a","container":"app"}
{"action":"focus","pod":"pod-b"}
```
Server → Client message types:
```jsonc
{"type":"awaitingPattern"}
{"type":"pods","data":{"pods":[{"name":"pod-a","namespace":"default","phase":"Running","restarts":0,"ready":1,"total":1}],"focus":"pod-a","pattern":"^api-"}}
{"type":"pod","data":{ /* full focused pod view */ }}
{"type":"log","pod":"pod-a","container":"app","line":"..."}
{"type":"event","data":{ "pod":"pod-a","type":"Warning","reason":"BackOff","message":"...","ageSeconds":120 }}
{"type":"metrics","data":{"containers":[{"name":"app","cpu":12,"memoryMiB":34.5}]}}
```

### Pod View Object (focused pod)
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
      "env": [ {"name":"ENV_MODE","value":"prod"}, {"name":"SECRET_TOKEN","value":"*** (secret mysecret/token)"} ]
    }
  ]
}
```

## Metrics
Uses metrics.k8s.io pod endpoint; absence produces `{ "disabled": true }` message.

## Env Var Sources
- Literal value
- SecretKeyRef → masked (`*** (secret name/key)`)
- ConfigMapKeyRef → `configmap:name/key`
- FieldRef → `fieldRef:spec.nodeName` etc.
- ResourceFieldRef → `resourceField:limits.cpu`

## Refresh Strategy
- Pods listing every 5s OR immediately on pattern change via an asyncio Event.
- Events polled every ~6s with v1->core fallback.
- Metrics polled at configured interval for focused pod only.
- Logs streaming tasks per (pod,container) with on-demand subscription.

## Development
```
python -m venv .venv
source .venv/bin/activate
pip install -e .

kubeluma serve            # interactive pattern
kubeluma serve --pod mypod # immediate pattern
```
## License
Internal / TBD.
