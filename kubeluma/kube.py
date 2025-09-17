from __future__ import annotations
import asyncio
import os
import time
import threading
from typing import Optional, Callable, Dict, Any
from kubernetes import client, config, watch
from kubernetes.client import ApiException

class KubeContext:
    def __init__(self, core: client.CoreV1Api, events: client.EventsV1Api, metrics: Optional[client.CustomObjectsApi], apps: client.AppsV1Api):
        self.core = core
        self.events = events
        self.metrics = metrics
        self.apps = apps

async def load_kube(kubeconfig: Optional[str], context: Optional[str]) -> KubeContext:
    def _load():
        if kubeconfig or context:
            config.load_kube_config(config_file=kubeconfig, context=context)
        else:
            try:
                config.load_kube_config()
            except Exception:
                config.load_incluster_config()
        return client.CoreV1Api(), client.EventsV1Api(), client.CustomObjectsApi(), client.AppsV1Api()
    loop = asyncio.get_event_loop()
    core, events, custom, apps = await loop.run_in_executor(None, _load)
    return KubeContext(core, events, custom, apps)

async def fetch_pod(core: client.CoreV1Api, namespace: Optional[str], name: str) -> Optional[Dict[str, Any]]:
    loop = asyncio.get_event_loop()
    def _get():
        try:
            ns = namespace or "default"
            return core.read_namespaced_pod(name=name, namespace=ns)
        except ApiException as e:
            if e.status == 404:
                return None
            raise
    pod = await loop.run_in_executor(None, _get)
    if pod is None:
        return None
    return pod.to_dict()

async def stream_logs(core: client.CoreV1Api, namespace: str, pod: str, container: str, line_cb: Callable[[str], None], stop_event: threading.Event):
    def _stream():
        try:
            resp = core.read_namespaced_pod_log(name=pod, namespace=namespace, container=container, follow=True, _preload_content=False, tail_lines=200)
            for line in resp.stream():  # type: ignore
                if stop_event.is_set():
                    break
                try:
                    decoded = line.decode('utf-8', 'replace').rstrip('\n')
                except Exception:
                    decoded = str(line)
                line_cb(decoded)
        except Exception as e:
            line_cb(f"[log-stream-error] {e}")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _stream)

async def fetch_metrics(custom: client.CustomObjectsApi, namespace: str, pod: str) -> Optional[Dict[str, Any]]:
    loop = asyncio.get_event_loop()
    group = "metrics.k8s.io"
    version = "v1beta1"
    plural = "pods"
    def _get():
        try:
            return custom.get_namespaced_custom_object(group, version, namespace, plural, pod)
        except ApiException as e:
            if e.status == 404:
                return None
            raise
        except Exception:
            return None
    return await loop.run_in_executor(None, _get)
