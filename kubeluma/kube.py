"""
Kubernetes client and API interactions for Kubeluma.

This module provides the interface between Kubeluma and the Kubernetes API.
It handles connection management, pod operations, log streaming, and metrics
retrieval with proper error handling and async support.

Key Components:
- KubeContext: Container for Kubernetes API clients
- load_kube: Initialize Kubernetes client with config loading
- fetch_pod: Retrieve individual pod information
- stream_logs: Stream container logs in real-time
- fetch_metrics: Retrieve pod resource metrics

The module supports both in-cluster and external Kubernetes configurations,
with automatic fallback between different authentication methods.

Example:
    ```python
    kube = await load_kube(kubeconfig="/path/to/config", context="my-context")
    pod_data = await fetch_pod(kube.core, "default", "my-pod")
    ```
"""

from __future__ import annotations
import asyncio
import os
import time
import threading
from typing import Optional, Callable, Dict, Any, Pattern
from kubernetes import client, config, watch
from kubernetes.client import ApiException

class KubeContext:
    """
    Container for Kubernetes API clients.
    
    Provides a unified interface to various Kubernetes API clients used throughout
    the Kubeluma application. This class encapsulates the different API clients
    needed for pod operations, events, metrics, and applications.
    
    Attributes:
        core: CoreV1Api client for pod and namespace operations
        events: EventsV1Api client for Kubernetes events
        metrics: CustomObjectsApi client for metrics (may be None if metrics server unavailable)
        apps: AppsV1Api client for application resources
        
    Example:
        ```python
        kube = await load_kube(kubeconfig, context)
        pods = kube.core.list_pod_for_all_namespaces()
        events = kube.events.list_namespaced_event(namespace="default")
        ```
    """
    
    def __init__(self, core: client.CoreV1Api, events: client.EventsV1Api, metrics: Optional[client.CustomObjectsApi], apps: client.AppsV1Api):
        """
        Initialize Kubernetes context with API clients.
        
        Args:
            core: CoreV1Api client for core Kubernetes resources
            events: EventsV1Api client for Kubernetes events
            metrics: CustomObjectsApi client for metrics (optional)
            apps: AppsV1Api client for application resources
        """
        self.core = core
        self.events = events
        self.metrics = metrics
        self.apps = apps

async def load_kube(kubeconfig: Optional[str], context: Optional[str]) -> KubeContext:
    """
    Load and initialize Kubernetes API clients.
    
    Loads Kubernetes configuration and creates API clients for various Kubernetes
    resources. Supports both external kubeconfig files and in-cluster configuration
    with automatic fallback.
    
    Args:
        kubeconfig: Path to kubeconfig file (optional, uses default if None)
        context: Kubernetes context name (optional, uses current context if None)
        
    Returns:
        KubeContext: Initialized context with all API clients
        
    Raises:
        Exception: If Kubernetes configuration cannot be loaded
        
    Example:
        ```python
        # Load with default configuration
        kube = await load_kube(None, None)
        
        # Load with specific kubeconfig and context
        kube = await load_kube("/path/to/config", "my-context")
        ```
    """
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
    """
    Fetch a specific pod by name and namespace.
    
    Retrieves detailed information about a single pod from the Kubernetes API.
    Returns None if the pod is not found (404 error), but raises other API exceptions.
    
    Args:
        core: CoreV1Api client for Kubernetes operations
        namespace: Namespace containing the pod (uses "default" if None)
        name: Name of the pod to fetch
        
    Returns:
        Optional[Dict[str, Any]]: Pod data as dictionary, or None if not found
        
    Raises:
        ApiException: For API errors other than 404 (pod not found)
        
    Example:
        ```python
        pod_data = await fetch_pod(kube.core, "default", "my-pod")
        if pod_data:
            print(f"Pod status: {pod_data['status']['phase']}")
        else:
            print("Pod not found")
        ```
    """
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

async def stream_logs(core: client.CoreV1Api, namespace: str, pod: str, container: str, line_cb: Callable[[str], None], stop_event: threading.Event) -> None:
    """
    Stream container logs in real-time.
    
    Continuously streams logs from a specific container in a pod, calling the
    provided callback function for each log line. The streaming continues until
    the stop event is set or an error occurs.
    
    Args:
        core: CoreV1Api client for Kubernetes operations
        namespace: Namespace containing the pod
        pod: Name of the pod
        container: Name of the container to stream logs from
        line_cb: Callback function called for each log line
        stop_event: Threading event to signal when to stop streaming
        
    Example:
        ```python
        import threading
        
        stop = threading.Event()
        def log_callback(line):
            print(f"Log: {line}")
        
        await stream_logs(kube.core, "default", "my-pod", "app", log_callback, stop)
        ```
    """
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
    """
    Fetch pod resource metrics from the metrics server.
    
    Retrieves CPU and memory usage metrics for a specific pod from the Kubernetes
    metrics server. Returns None if metrics are not available or the pod is not found.
    
    Args:
        custom: CustomObjectsApi client for metrics operations
        namespace: Namespace containing the pod
        pod: Name of the pod to fetch metrics for
        
    Returns:
        Optional[Dict[str, Any]]: Metrics data as dictionary, or None if unavailable
        
    Note:
        Requires metrics-server to be installed and running in the cluster.
        Returns None if metrics server is not available.
        
    Example:
        ```python
        metrics = await fetch_metrics(kube.metrics, "default", "my-pod")
        if metrics:
            for container in metrics.get('containers', []):
                print(f"CPU: {container['usage']['cpu']}")
        ```
    """
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
