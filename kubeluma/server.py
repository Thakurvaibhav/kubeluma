from .dependencies import asyncio, json, re, time, dataclass, field, Dict, Any, Optional, Set, Path, FastAPI, WebSocket, WebSocketDisconnect, HTMLResponse, StaticFiles
from .kube import load_kube, fetch_metrics, stream_logs
import os
import logging

# Logging setup (level via KUBELUMA_LOG_LEVEL env or default INFO)
logging.basicConfig(level=getattr(logging, os.getenv('KUBELUMA_LOG_LEVEL','INFO').upper(), logging.INFO), format='[%(asctime)s] %(levelname)s %(message)s')
log = logging.getLogger('kubeluma')
# Helper for safe exception logging
def _exc(msg: str, exc: Exception):
    log.warning(f"{msg}: {exc.__class__.__name__}: {exc}")

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
    log.info("[ws] client connected")
    hub.clients.add(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                log.debug("[ws] discard non-json message")
                continue
            action = msg.get('action')
            if action == 'subscribe' and msg.get('channel')=='pod':
                log.debug("[ws] subscribe pod summary")
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
                log.debug(f"[ws] subscribe logs key={key}")
            elif action == 'focus':
                pod = msg.get('pod')
                if pod in hub.pods:
                    old = hub.focus_pod
                    hub.focus_pod = pod
                    log.info(f"[focus] changed {old} -> {pod}")
                    await hub.broadcast({'type':'pod','data':hub.pods[pod]})
    except WebSocketDisconnect:
        log.info("[ws] client disconnected")
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
        log.info(f"[pattern] set pattern='{pattern}'")
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
    POD_REFRESH_SEC = int(os.getenv('KUBELUMA_POD_REFRESH_SEC','5'))
    log.info(f"[pods] refresh interval={POD_REFRESH_SEC}s")

    async def refresh_pods():
        last_broadcast_keys: Set[str] = set()
        while True:
            loop = asyncio.get_event_loop()
            def _list():
                try:
                    if namespace:
                        return kube.core.list_namespaced_pod(namespace=namespace)
                    return kube.core.list_pod_for_all_namespaces()
                except Exception as exc:
                    _exc('[pods] list error', exc)
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
                # Always update hub.pods (even if empty) so deletions reflect
                prev_keys = set(hub.pods.keys())
                new_keys = set(pods_view.keys())
                if new_keys != prev_keys:
                    changed = True
                    log.info(f"[pods] key change prev={len(prev_keys)} new={len(new_keys)} added={len(new_keys-prev_keys)} removed={len(prev_keys-new_keys)}")
                hub.pods = pods_view
                # Focus management
                if hub.pods:
                    if not hub.focus_pod or hub.focus_pod not in hub.pods:
                        hub.focus_pod = sorted(hub.pods.keys())[0]
                        changed = True
                        log.info(f"[pods] focus set {hub.focus_pod}")
                else:
                    if hub.focus_pod is not None:
                        hub.focus_pod = None
                        changed = True
                        log.info("[pods] focus cleared (no matches)")
                if changed:
                    pods_summary = []
                    for n,pv in hub.pods.items():
                        restarts = sum(c['restarts'] for c in pv['containers'])
                        ready = sum(1 for c in pv['containers'] if c['ready'])
                        pods_summary.append({'name':n,'namespace':pv['namespace'],'phase':pv['phase'],'restarts':restarts,'ready':ready,'total':len(pv['containers'])})
                    await hub.broadcast({'type':'pods','data':{'pods':pods_summary,'focus':hub.focus_pod,'pattern':hub.regex_text}})
                    if hub.focus_pod:
                        await hub.broadcast({'type':'pod','data':hub.pods[hub.focus_pod]})
                last_broadcast_keys = new_keys
            elif not hub.regex:
                await hub.broadcast({'type':'awaitingPattern'})
            # wait for either event or timeout
            try:
                hub.refresh_event.clear()
                await asyncio.wait_for(hub.refresh_event.wait(), timeout=POD_REFRESH_SEC)
            except asyncio.TimeoutError:
                pass

    async def poll_metrics():
        while True:
            if hub.focus_pod and kube.metrics and hub.focus_pod in hub.pods:
                try:
                    ns = hub.pods[hub.focus_pod]['namespace']
                    nm = hub.pods[hub.focus_pod]['name']
                    start = time.time()
                    m = await fetch_metrics(kube.metrics, ns, nm)
                    dur = (time.time()-start)*1000
                    log.debug(f"[metrics] pod={nm} fetched in {dur:.1f}ms present={bool(m)}")
                    if m:
                        hub.metrics[hub.focus_pod] = metrics_to_view(m, hub.pods.get(hub.focus_pod))
                        await hub.broadcast({'type':'metrics','data':hub.metrics[hub.focus_pod]})
                    else:
                        await hub.broadcast({'type':'metrics','data':{'disabled':True}})
                except Exception as exc:
                    _exc('[metrics] error', exc)
                    await hub.broadcast({'type':'metrics','data':{'disabled':True}})
            await asyncio.sleep(metrics_interval)

    async def poll_events():
        # store uid -> first_seen_ts so memory does not grow unbounded
        seen: Dict[str,float] = {}
        SEEN_MAX = 5000
        SEEN_TTL = 3600  # seconds
        while True:
            if hub.pods:
                ns = namespace or next(iter(hub.pods.values()))['namespace']
                if ns:
                    pod_uids = {pv['uid'] for pv in hub.pods.values()}
                    pod_names = {pv['name'] for pv in hub.pods.values()}
                    loop = asyncio.get_event_loop()
                    cycle_id = int(time.time())
                    log.info(f"[events] cycle={cycle_id} namespace={ns} pods={len(pod_names)} uids={len(pod_uids)}")
                    try:
                        def _list_events_v1():
                            try:
                                return kube.events.list_namespaced_event(namespace=ns)
                            except Exception as e:
                                log.debug(f"[events] v1beta events API error: {e}")
                                return None
                        def _list_core():
                            try:
                                return kube.core.list_namespaced_event(namespace=ns)
                            except Exception as e:
                                log.debug(f"[events] core events API error: {e}")
                                return None
                        ev_list = await loop.run_in_executor(None, _list_events_v1)
                        src = 'events.k8s.io'
                        if not ev_list or not getattr(ev_list, 'items', None):
                            ev_list = await loop.run_in_executor(None, _list_core)
                            src = 'core'
                        total_items = len(getattr(ev_list, 'items', []) or [])
                        log.info(f"[events] cycle={cycle_id} source={src} total_items={total_items}")
                        matched = skipped_seen = skipped_other = 0
                        now_ts = time.time()
                        for e in getattr(ev_list, 'items', []) or []:
                            try:
                                uid = getattr(e.metadata, 'uid', None)
                                if not uid:
                                    skipped_other += 1
                                    continue
                                if uid in seen:
                                    skipped_seen += 1
                                    continue
                                regarding = getattr(e, 'regarding', None) or getattr(e, 'involved_object', None)
                                r_name = getattr(regarding, 'name', None) if regarding else None
                                r_uid = getattr(regarding, 'uid', None) if regarding else None
                                if not r_name:
                                    skipped_other += 1
                                    continue
                                if r_uid not in pod_uids and r_name not in pod_names:
                                    skipped_other += 1
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
                                seen[uid] = now_ts
                                matched += 1
                                await hub.broadcast({'type':'event','data':data})
                            except Exception as ex:
                                skipped_other += 1
                                log.debug(f"[events] cycle={cycle_id} exception processing event: {ex}")
                                continue
                        # prune seen
                        if len(seen) > SEEN_MAX:
                            before = len(seen)
                            cutoff = time.time() - SEEN_TTL
                            for k,v in list(seen.items()):
                                if v < cutoff:
                                    seen.pop(k, None)
                            # if still too big, drop oldest
                            if len(seen) > SEEN_MAX:
                                for k,_ in sorted(seen.items(), key=lambda kv: kv[1])[:len(seen)-SEEN_MAX]:
                                    seen.pop(k, None)
                            pruned = before - len(seen)
                            if pruned:
                                log.info(f"[events] pruned {pruned} old seen entries size={len(seen)}")
                        log.info(f"[events] cycle={cycle_id} matched={matched} skipped_seen={skipped_seen} skipped_other={skipped_other} seen_size={len(seen)}")
                    except Exception as ex:
                        log.warning(f"[events] cycle error: {ex}")
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
    config = uvicorn.Config(app, host=host, port=port, log_level=os.getenv('KUBELUMA_UVICORN_LEVEL','info'))
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
        # collect env vars (existing logic retained)
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
        # NEW: capture resource requests / limits
        res_req = {}
        res_lim = {}
        try:
            if sc and getattr(sc, 'resources', None):
                rq = getattr(sc.resources, 'requests', None) or {}
                lm = getattr(sc.resources, 'limits', None) or {}
                for k in ('cpu','memory'):
                    if rq.get(k):
                        res_req[k] = rq.get(k)
                    if lm.get(k):
                        res_lim[k] = lm.get(k)
        except Exception:
            pass
        containers.append({
            'name': cstat.name,
            'ready': cstat.ready,
            'restarts': cstat.restart_count,
            'state': state,
            'image': cstat.image,
            'env': env_list,
            'resources': {'requests': res_req, 'limits': res_lim}
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

# Configurable thresholds (percent of limit) with defaults
CPU_LIMIT_RED_PCT = int(os.getenv('KUBELUMA_CPU_LIMIT_RED_PCT', '90'))
MEM_LIMIT_RED_PCT = int(os.getenv('KUBELUMA_MEM_LIMIT_RED_PCT', '80'))

# Replace metrics_to_view with percentage-aware version

def metrics_to_view(m, pod_view=None):
    # Build resource map {container: {'requests':..., 'limits':...}}
    res_map = {}
    if pod_view:
        for c in pod_view.get('containers', []):
            res_map[c['name']] = c.get('resources') or {}
    containers = []
    for c in m.get('containers', []):
        name = c['name']
        usage = c.get('usage', {})
        cpu_raw = usage.get('cpu', '0')
        mem_raw = usage.get('memory', '0')
        def parse_cpu(v):
            try:
                if v.endswith('n'): return int(v[:-1]) / 1_000_000  # n -> m
                if v.endswith('m'): return int(v[:-1])
                return float(v) * 1000  # cores -> m
            except Exception:
                return 0
        def parse_mem(v):
            try:
                if v.endswith('Ki'): return round(int(v[:-2]) / 1024, 2)
                if v.endswith('Mi'): return float(v[:-2])
                if v.endswith('Gi'): return float(v[:-2]) * 1024
                if v.endswith('Ti'): return float(v[:-2]) * 1024 * 1024
                return 0.0
            except Exception:
                return 0.0
        cpu_m = parse_cpu(cpu_raw)
        mem_mib = parse_mem(mem_raw)
        req_cpu = lim_cpu = req_mem = lim_mem = None
        pct_cpu_req = pct_cpu_lim = pct_mem_req = pct_mem_lim = None
        if name in res_map:
            rq = (res_map[name].get('requests') or {})
            lm = (res_map[name].get('limits') or {})
            if 'cpu' in rq:
                req_cpu = parse_cpu(rq['cpu'])
                if req_cpu: pct_cpu_req = round((cpu_m/req_cpu)*100,1)
            if 'cpu' in lm:
                lim_cpu = parse_cpu(lm['cpu'])
                if lim_cpu: pct_cpu_lim = round((cpu_m/lim_cpu)*100,1)
            if 'memory' in rq:
                req_mem = parse_mem(rq['memory'])
                if req_mem: pct_mem_req = round((mem_mib/req_mem)*100,1)
            if 'memory' in lm:
                lim_mem = parse_mem(lm['memory'])
                if lim_mem: pct_mem_lim = round((mem_mib/lim_mem)*100,1)
        containers.append({
            'name': name,
            'cpu': cpu_m,
            'memoryMiB': mem_mib,
            'cpuRequest': req_cpu,
            'cpuLimit': lim_cpu,
            'memRequestMiB': req_mem,
            'memLimitMiB': lim_mem,
            'cpuPctOfRequest': pct_cpu_req,
            'cpuPctOfLimit': pct_cpu_lim,
            'memPctOfRequest': pct_mem_req,
            'memPctOfLimit': pct_mem_lim,
        })
    return {'containers': containers, 'thresholds': {'cpuLimitRed': CPU_LIMIT_RED_PCT, 'memLimitRed': MEM_LIMIT_RED_PCT}}
