"""
FastAPI server and WebSocket handling for Kubeluma.

This module provides the main web server for Kubeluma, including FastAPI routes,
WebSocket connections, and background task management. It handles real-time
communication between the web UI and Kubernetes cluster.

Key Components:
- Hub: Central state management for WebSocket connections and pod data
- FastAPI routes: HTTP endpoints for pattern management and UI serving
- WebSocket handling: Real-time communication with web clients
- Background tasks: Pod monitoring, metrics polling, and log streaming
- run_server: Main server startup and configuration

The server provides a REST API for pattern management and WebSocket endpoints
for real-time data streaming to connected clients.

Example:
    ```python
    # Start server programmatically
    await run_server(
        pod_pattern=re.compile("^api-"),
        namespace="production",
        port=8080,
        host="0.0.0.0"
    )
    ```
"""

import asyncio
import json
import re
import time
import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, Set, Pattern, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from .kube import load_kube, fetch_metrics, stream_logs
from .exceptions import InvalidPatternError, KubernetesConnectionError, MetricsUnavailableError
from .validation import validate_regex_pattern
from .tasks import refresh_pods_task, poll_metrics_task, poll_events_task, stream_logs_task
from .pod_processing import pod_to_view
from .metrics_processing import metrics_to_view
from .constants import (
    SEEN_EVENTS_MAX, SEEN_EVENTS_TTL_SECONDS, DEFAULT_POD_REFRESH_SECONDS,
    DEFAULT_EVENTS_POLL_INTERVAL_SECONDS, DEFAULT_LOG_STREAM_CHECK_INTERVAL_SECONDS,
    DEFAULT_CPU_LIMIT_RED_PERCENT, DEFAULT_MEM_LIMIT_RED_PERCENT,
    MAX_EVENTS_HISTORY, MAX_RECENT_EVENTS_DISPLAY, DEFAULT_LOG_LEVEL,
    DEFAULT_UVICORN_LOG_LEVEL
)

# Logging setup (level via KUBELUMA_LOG_LEVEL env or default INFO)
logging.basicConfig(
    level=getattr(logging, os.getenv('KUBELUMA_LOG_LEVEL', DEFAULT_LOG_LEVEL).upper(), logging.INFO),
    format='[%(asctime)s] %(levelname)s %(message)s'
)
log = logging.getLogger('kubeluma')

# Helper for safe exception logging
def _log_exception(msg: str, exc: Exception, level: int = logging.WARNING):
    """Log an exception with proper formatting."""
    log.log(level, f"{msg}: {exc.__class__.__name__}: {exc}")

# Load HTML from file
try:
    INDEX_HTML = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
except FileNotFoundError:
    INDEX_HTML = """<!DOCTYPE html><html><body><h2>Kubeluma</h2><p>Embedded index.html missing in package. Reinstall with package data.</p></body></html>"""

@dataclass
class PodState:
    data: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)

class Hub:
    """
    Central state management for WebSocket connections and pod data.
    
    The Hub class manages all WebSocket connections, pod data, and application state.
    It provides methods for broadcasting messages to connected clients and managing
    the focus state for pod inspection.
    
    Attributes:
        clients: Set of connected WebSocket clients
        focus_pod: Currently focused pod name
        pods: Dictionary of pod data keyed by pod name
        logs_subs: Dictionary of log subscriptions keyed by "pod::container"
        metrics: Dictionary of metrics data keyed by pod name
        regex: Compiled regex pattern for pod filtering
        regex_text: Original regex pattern text
        refresh_event: Event for triggering immediate pod refresh
        
    Example:
        ```python
        hub = Hub()
        await hub.broadcast({"type": "pods", "data": {...}})
        ```
    """
    
    def __init__(self):
        """Initialize the Hub with empty state."""
        self.clients: Set[WebSocket] = set()
        self.focus_pod: Optional[str] = None
        self.pods: Dict[str, Dict[str, Any]] = {}
        self.logs_subs: Dict[str, Set[WebSocket]] = {}
        self.metrics: Dict[str, Dict[str, Any]] = {}
        self.regex: Optional[Pattern[str]] = None
        self.regex_text: Optional[str] = None
        self.refresh_event: Optional[asyncio.Event] = None

    async def broadcast(self, msg: Dict[str, Any]) -> None:
        """Broadcast message to all connected WebSocket clients."""
        if not self.clients:
            return
            
        dead = []
        try:
            txt = json.dumps(msg, separators=(',', ':'))
        except (TypeError, ValueError) as e:
            _log_exception("[broadcast] Failed to serialize message", e)
            return
            
        for ws in list(self.clients):
            try:
                await ws.send_text(txt)
            except Exception as e:
                _log_exception(f"[broadcast] Failed to send to client", e)
                dead.append(ws)
                
        # Clean up dead connections
        for d in dead:
            self.clients.discard(d)
            # Also remove from log subscriptions
            for subs in self.logs_subs.values():
                subs.discard(d)

hub = Hub()
app = FastAPI()

@app.get("/")
async def index():
    return HTMLResponse(INDEX_HTML)

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    log.info("[ws] client connected")
    hub.clients.add(ws)
    try:
        while True:
            try:
                raw = await ws.receive_text()
                msg = json.loads(raw)
            except json.JSONDecodeError as e:
                log.warning(f"[ws] Invalid JSON received: {e}")
                continue
            except Exception as e:
                _log_exception("[ws] Error receiving message", e)
                break
            
            action = msg.get('action')
            if action == 'subscribe' and msg.get('channel') == 'pod':
                log.debug("[ws] subscribe pod summary")
                try:
                    if hub.pods:
                        pods_summary = []
                        for n, pv in hub.pods.items():
                            restarts = sum(c['restarts'] for c in pv['containers'])
                            ready = sum(1 for c in pv['containers'] if c['ready'])
                            pods_summary.append({
                                'name': n, 'namespace': pv['namespace'], 'phase': pv['phase'],
                                'restarts': restarts, 'ready': ready, 'total': len(pv['containers'])
                            })
                        await ws.send_text(json.dumps({
                            'type': 'pods', 'data': {'pods': pods_summary, 'focus': hub.focus_pod}
                        }))
                    if hub.focus_pod and hub.focus_pod in hub.pods:
                        await ws.send_text(json.dumps({'type': 'pod', 'data': hub.pods[hub.focus_pod]}))
                except Exception as e:
                    _log_exception("[ws] Error handling pod subscription", e)
                    
            elif action == 'subscribe' and msg.get('channel') == 'logs':
                pod = msg.get('pod')
                container = msg.get('container')
                if not pod or not container:
                    log.warning("[ws] Invalid logs subscription - missing pod or container")
                    continue
                key = f"{pod}::{container}"
                hub.logs_subs.setdefault(key, set()).add(ws)
                log.debug(f"[ws] subscribe logs key={key}")
                
            elif action == 'focus':
                pod = msg.get('pod')
                if not pod:
                    log.warning("[ws] Invalid focus request - missing pod name")
                    continue
                if pod in hub.pods:
                    old = hub.focus_pod
                    hub.focus_pod = pod
                    log.info(f"[focus] changed {old} -> {pod}")
                    try:
                        await hub.broadcast({'type': 'pod', 'data': hub.pods[pod]})
                    except Exception as e:
                        _log_exception("[ws] Error broadcasting focus change", e)
                else:
                    log.warning(f"[ws] Focus request for unknown pod: {pod}")
                    
    except WebSocketDisconnect:
        log.info("[ws] client disconnected")
    except Exception as e:
        _log_exception("[ws] WebSocket error", e)
    finally:
        hub.clients.discard(ws)
        for subs in hub.logs_subs.values():
            subs.discard(ws)

@app.post('/api/set_pattern')
async def set_pattern(payload: Dict[str, str]):
    pattern = payload.get('pattern')
    if not pattern:
        raise HTTPException(status_code=400, detail="Pattern is required")
    
    try:
        hub.regex = validate_regex_pattern(pattern)
        hub.regex_text = pattern
        log.info(f"[pattern] set pattern='{pattern}'")
    except InvalidPatternError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    hub.focus_pod = None
    hub.pods = {}
    if hub.refresh_event:
        hub.refresh_event.set()
    return {'ok': True, 'pattern': pattern}

@app.post('/api/reset_pattern')
async def reset_pattern():
    hub.regex = None
    hub.regex_text = None
    hub.focus_pod = None
    hub.pods = {}
    if hub.refresh_event:
        hub.refresh_event.set()
    await hub.broadcast({'type':'awaitingPattern'})
    return {'ok': True}

@app.get('/api/current_pattern')
async def current_pattern():
    return {'pattern': hub.regex_text}

async def run_server(
    pod_pattern: Optional[Pattern[str]], 
    namespace: Optional[str], 
    kubeconfig: Optional[str], 
    context: Optional[str], 
    port: int, 
    metrics_interval: float, 
    host: str = '127.0.0.1'
) -> None:
    """Run the Kubeluma server with proper error handling."""
    try:
        kube = await load_kube(kubeconfig, context)
    except Exception as e:
        _log_exception("[server] Failed to load Kubernetes configuration", e)
        raise KubernetesConnectionError(f"Failed to connect to Kubernetes: {e}")
    
    hub.regex = pod_pattern  # may be None until set via API
    hub.regex_text = getattr(pod_pattern, 'pattern', None) if pod_pattern else None
    hub.refresh_event = asyncio.Event()
    
    try:
        POD_REFRESH_SEC = int(os.getenv('KUBELUMA_POD_REFRESH_SEC', str(DEFAULT_POD_REFRESH_SECONDS)))
    except ValueError:
        POD_REFRESH_SEC = DEFAULT_POD_REFRESH_SECONDS
        log.warning(f"[server] Invalid KUBELUMA_POD_REFRESH_SEC, using default: {POD_REFRESH_SEC}")
    
    log.info(f"[pods] refresh interval={POD_REFRESH_SEC}s")

    # Start background tasks
    loop = asyncio.get_event_loop()
    loop.create_task(refresh_pods_task(kube, hub, namespace, POD_REFRESH_SEC))
    loop.create_task(poll_metrics_task(kube, hub, metrics_interval))
    loop.create_task(poll_events_task(kube, hub, namespace))
    loop.create_task(stream_logs_task(kube, hub))

    import uvicorn
    uvicorn_log_level = os.getenv('KUBELUMA_UVICORN_LEVEL', DEFAULT_UVICORN_LOG_LEVEL)
    config = uvicorn.Config(app, host=host, port=port, log_level=uvicorn_log_level)
    server = uvicorn.Server(config)
    await server.serve()

# Configuration validation for thresholds
try:
    CPU_LIMIT_RED_PCT = int(os.getenv('KUBELUMA_CPU_LIMIT_RED_PCT', str(DEFAULT_CPU_LIMIT_RED_PERCENT)))
except ValueError:
    CPU_LIMIT_RED_PCT = DEFAULT_CPU_LIMIT_RED_PERCENT
    log.warning(f"[config] Invalid KUBELUMA_CPU_LIMIT_RED_PCT, using default: {CPU_LIMIT_RED_PCT}")

try:
    MEM_LIMIT_RED_PCT = int(os.getenv('KUBELUMA_MEM_LIMIT_RED_PCT', str(DEFAULT_MEM_LIMIT_RED_PERCENT)))
except ValueError:
    MEM_LIMIT_RED_PCT = DEFAULT_MEM_LIMIT_RED_PERCENT
    log.warning(f"[config] Invalid KUBELUMA_MEM_LIMIT_RED_PCT, using default: {MEM_LIMIT_RED_PCT}")
