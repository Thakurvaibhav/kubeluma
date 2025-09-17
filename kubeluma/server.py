from .dependencies import asyncio, json, re, time, dataclass, field, Dict, Any, Optional, Set, Path, FastAPI, WebSocket, WebSocketDisconnect, HTMLResponse, StaticFiles
from .kube import load_kube, fetch_metrics, stream_logs

# Load HTML from file
INDEX_HTML = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')

@dataclass
class PodState:
    data: Dict[str, Any] = field(default_factory=dict)
    events: list = field(default_factory=list)

class Hub:
    def __init__(self):
        self.clients: Set[WebSocket] = set()
        self.focus_pod: Optional[str] = None
        self.pods: Dict[str, Dict[str, Any]] = {}
        self.logs_subs: Dict[str, Set[WebSocket]] = {}
        self.metrics: Dict[str, Dict[str, Any]] = {}
        self.regex: Optional[re.Pattern] = None
        self.regex_text: Optional[str] = None
        self.refresh_event: Optional[asyncio.Event] = None

    async def broadcast(self, msg: Dict[str, Any]):
        dead = []
        txt = json.dumps(msg, separators=(',',':'))
        for ws in list(self.clients):
            try:
                await ws.send_text(txt)
            except Exception:
                dead.append(ws)
        for d in dead:
            self.clients.discard(d)

hub = Hub()
app = FastAPI()

@app.get("/")
async def index():
    return HTMLResponse(INDEX_HTML)

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    hub.clients.add(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            action = msg.get('action')
            if action == 'subscribe' and msg.get('channel')=='pod':
                if hub.pods:
                    pods_summary = []
                    for n,pv in hub.pods.items():
                        restarts = sum(c['restarts'] for c in pv['containers'])
                        ready = sum(1 for c in pv['containers'] if c['ready'])
                        pods_summary.append({'name':n,'namespace':pv['namespace'],'phase':pv['phase'],'restarts':restarts,'ready':ready,'total':len(pv['containers'])})
                    await ws.send_text(json.dumps({'type':'pods','data':{'pods':pods_summary,'focus':hub.focus_pod}}))
                if hub.focus_pod and hub.focus_pod in hub.pods:
                    await ws.send_text(json.dumps({'type':'pod','data':hub.pods[hub.focus_pod]}))
            elif action == 'subscribe' and msg.get('channel')=='logs':
                key = f"{msg.get('pod')}::{msg.get('container')}"
                hub.logs_subs.setdefault(key,set()).add(ws)
            elif action == 'focus':
                pod = msg.get('pod')
                if pod in hub.pods:
                    hub.focus_pod = pod
                    await hub.broadcast({'type':'pod','data':hub.pods[pod]})
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)
        for subs in hub.logs_subs.values():
            subs.discard(ws)

@app.post('/api/set_pattern')
async def set_pattern(payload: Dict[str, str]):
    pattern = payload.get('pattern')
    if not pattern:
        return {'error':'pattern required'}
    try:
        hub.regex = re.compile(pattern)
        hub.regex_text = pattern
    except re.error as e:
        return {'error': f'invalid regex: {e}'}
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

async def run_server(pod_pattern, namespace, kubeconfig, context, port, metrics_interval, host='127.0.0.1'):
    kube = await load_kube(kubeconfig, context)
    hub.regex = pod_pattern  # may be None until set via API
    hub.regex_text = getattr(pod_pattern, 'pattern', None) if pod_pattern else None
    hub.refresh_event = asyncio.Event()

    async def refresh_pods():
        while True:
            loop = asyncio.get_event_loop()
            def _list():
                try:
                    if namespace:
                        return kube.core.list_namespaced_pod(namespace=namespace)
                    return kube.core.list_pod_for_all_namespaces()
                except Exception:
                    return None
            plist = await loop.run_in_executor(None, _list)
            changed = False
            if plist and getattr(plist, 'items', None) and hub.regex:
                pods_view: Dict[str, Dict[str, Any]] = {}
                for p in plist.items:
                    name = p.metadata.name
                    if not hub.regex.search(name):
                        continue
                    pods_view[name] = pod_to_view(p)
                if pods_view:
                    if set(pods_view.keys()) != set(hub.pods.keys()):
                        changed = True
                    hub.pods = pods_view
                    if not hub.focus_pod or hub.focus_pod not in hub.pods:
                        hub.focus_pod = sorted(hub.pods.keys())[0]
                        changed = True
                    pods_summary = []
                    for n,pv in hub.pods.items():
                        restarts = sum(c['restarts'] for c in pv['containers'])
                        ready = sum(1 for c in pv['containers'] if c['ready'])
                        pods_summary.append({'name':n,'namespace':pv['namespace'],'phase':pv['phase'],'restarts':restarts,'ready':ready,'total':len(pv['containers'])})
                    await hub.broadcast({'type':'pods','data':{'pods':pods_summary,'focus':hub.focus_pod,'pattern':hub.regex_text}})
                    if changed:
                        await hub.broadcast({'type':'pod','data':hub.pods[hub.focus_pod]})
            elif not hub.regex:
                await hub.broadcast({'type':'awaitingPattern'})
            # wait for either event or timeout
            try:
                hub.refresh_event.clear()
                await asyncio.wait_for(hub.refresh_event.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

    async def poll_metrics():
        while True:
            if hub.focus_pod and kube.metrics and hub.focus_pod in hub.pods:
                try:
                    ns = hub.pods[hub.focus_pod]['namespace']
                    nm = hub.pods[hub.focus_pod]['name']
                    m = await fetch_metrics(kube.metrics, ns, nm)
                    if m:
                        hub.metrics[hub.focus_pod] = metrics_to_view(m)
                        await hub.broadcast({'type':'metrics','data':hub.metrics[hub.focus_pod]})
                    else:
                        await hub.broadcast({'type':'metrics','data':{'disabled':True}})
                except Exception:
                    await hub.broadcast({'type':'metrics','data':{'disabled':True}})
            await asyncio.sleep(metrics_interval)

    async def poll_events():
        seen: Set[str] = set()
        while True:
            if hub.pods:
                ns = namespace or next(iter(hub.pods.values()))['namespace']
                if ns:
                    pod_uids = {pv['uid'] for pv in hub.pods.values()}
                    pod_names = {pv['name'] for pv in hub.pods.values()}
                    loop = asyncio.get_event_loop()
                    try:
                        def _list_events_v1():
                            try:
                                return kube.events.list_namespaced_event(namespace=ns)
                            except Exception:
                                return None
                        def _list_core():
                            try:
                                return kube.core.list_namespaced_event(namespace=ns)
                            except Exception:
                                return None
                        ev_list = await loop.run_in_executor(None, _list_events_v1)
                        if not ev_list or not getattr(ev_list, 'items', None):
                            ev_list = await loop.run_in_executor(None, _list_core)
                        for e in getattr(ev_list, 'items', []) or []:
                            try:
                                uid = getattr(e.metadata, 'uid', None)
                                if not uid or uid in seen:
                                    continue
                                regarding = getattr(e, 'regarding', None) or getattr(e, 'involved_object', None)
                                r_name = getattr(regarding, 'name', None) if regarding else None
                                r_uid = getattr(regarding, 'uid', None) if regarding else None
                                if not r_name:
                                    continue
                                if r_uid not in pod_uids and r_name not in pod_names:
                                    continue
                                evt_time = getattr(e, 'event_time', None)
                                ts = None
                                if evt_time:
                                    ts = getattr(evt_time, 'timestamp', lambda: None)() if callable(getattr(evt_time, 'timestamp', None)) else None
                                if ts is None:
                                    last_ts = getattr(e, 'last_timestamp', None) or getattr(e, 'deprecated_last_timestamp', None)
                                    if last_ts and hasattr(last_ts, 'timestamp'):
                                        ts = last_ts.timestamp()
                                age = int(time.time() - ts) if ts else 0
                                msg_txt = getattr(e, 'note', None) or getattr(e, 'message', '') or ''
                                data = {'pod': r_name,'type': getattr(e, 'type', '') or '','reason': getattr(e, 'reason', '') or '','message': msg_txt,'ageSeconds': age,'targetType': 'pod'}
                                seen.add(uid)
                                await hub.broadcast({'type':'event','data':data})
                            except Exception:
                                continue
                    except Exception:
                        pass
            await asyncio.sleep(6)

    async def stream_log_task():
        active = {}
        while True:
            if hub.focus_pod and hub.focus_pod in hub.pods:
                ns = hub.pods[hub.focus_pod]['namespace']
                name = hub.pods[hub.focus_pod]['name']
                for c in hub.pods[hub.focus_pod].get('containers', []):
                    key = f"{name}::{c['name']}"
                    subs = hub.logs_subs.get(key)
                    if subs and key not in active:
                        asyncio.create_task(follow_logs(ns, name, c['name'], key))
                        active[key]=True
            await asyncio.sleep(2)

    async def follow_logs(ns, pod, container, key):
        import threading
        stop = threading.Event()
        loop = asyncio.get_running_loop()
        async def _cb(line):
            subs = hub.logs_subs.get(key, set())
            if not subs:
                stop.set()
                return
            msg = json.dumps({'type':'log','pod':pod,'container':container,'line':line})
            for ws in list(subs):
                try:
                    await ws.send_text(msg)
                except Exception:
                    subs.discard(ws)
        def line_cb(line):
            asyncio.run_coroutine_threadsafe(_cb(line), loop)
        await stream_logs(kube.core, ns, pod, container, line_cb, stop)

    loop = asyncio.get_event_loop()
    loop.create_task(refresh_pods())
    loop.create_task(poll_metrics())
    loop.create_task(poll_events())
    loop.create_task(stream_log_task())

    import uvicorn
    config = uvicorn.Config(app, host=host, port=port, log_level='warning')
    server = uvicorn.Server(config)
    await server.serve()

# Helpers remain

def pod_to_view(p):
    status = p.status
    containers = []
    spec_map = {}
    try:
        for sc in getattr(p.spec, 'containers', []) or []:
            spec_map[sc.name] = sc
    except Exception:
        pass
    for cstat in status.container_statuses or []:
        state = 'unknown'
        if cstat.state.running:
            state = 'running'
        elif cstat.state.waiting:
            state = f"waiting({cstat.state.waiting.reason})"
        elif cstat.state.terminated:
            state = f"terminated({cstat.state.terminated.reason})"
        env_list = []
        sc = spec_map.get(cstat.name)
        if sc and getattr(sc, 'env', None):
            for ev in sc.env:
                try:
                    val_display = None
                    if ev.value is not None:
                        val_display = ev.value
                    elif ev.value_from:
                        src = ev.value_from
                        if getattr(src, 'secret_key_ref', None):
                            ref = src.secret_key_ref
                            val_display = f"*** (secret {ref.name}/{ref.key})"
                        elif getattr(src, 'config_map_key_ref', None):
                            ref = src.config_map_key_ref
                            val_display = f"configmap:{ref.name}/{ref.key}"
                        elif getattr(src, 'field_ref', None):
                            ref = src.field_ref
                            val_display = f"fieldRef:{ref.field_path}"
                        elif getattr(src, 'resource_field_ref', None):
                            ref = src.resource_field_ref
                            val_display = f"resourceField:{ref.resource}"
                        elif getattr(src, 'pod_field_ref', None):
                            ref = src.pod_field_ref
                            val_display = f"podField:{ref.field_path}"
                        else:
                            val_display = '(valueFrom)'
                    env_list.append({'name': ev.name, 'value': val_display})
                except Exception:
                    continue
        containers.append({
            'name': cstat.name,
            'ready': cstat.ready,
            'restarts': cstat.restart_count,
            'state': state,
            'image': cstat.image,
            'env': env_list,
        })
    age_seconds = 0
    if p.metadata.creation_timestamp:
        age_seconds = int(time.time() - p.metadata.creation_timestamp.timestamp())
    return {
        'name': p.metadata.name,
        'uid': p.metadata.uid,
        'namespace': p.metadata.namespace,
        'phase': status.phase,
        'node': status.host_ip,
        'podIP': getattr(status, 'pod_ip', None),
        'ageSeconds': age_seconds,
        'containers': containers,
    }

def metrics_to_view(m):
    containers = []
    for c in m.get('containers', []):
        name = c['name']
        usage = c.get('usage', {})
        cpu_raw = usage.get('cpu', '0')
        mem_raw = usage.get('memory', '0')
        def parse_cpu(v):
            if v.endswith('n'):
                return int(v[:-1]) / 1_000_000
            if v.endswith('m'):
                return int(v[:-1])
            return int(v) * 1000
        def parse_mem(v):
            if v.endswith('Ki'):
                return round(int(v[:-2]) / 1024, 2)
            if v.endswith('Mi'):
                return float(v[:-2])
            if v.endswith('Gi'):
                return float(v[:-2]) * 1024
            return 0.0
        containers.append({'name': name, 'cpu': parse_cpu(cpu_raw), 'memoryMiB': parse_mem(mem_raw)})
    return {'containers': containers}
