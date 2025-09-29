"""
Data models for Kubeluma.

This module defines the data structures and models used throughout the Kubeluma
application. It provides type-safe representations of Kubernetes resources,
metrics data, and application state.

Key Models:
- ContainerResource: Resource requests and limits for containers
- ContainerEnvVar: Environment variable representation
- ContainerInfo: Complete container information
- PodInfo: Pod information and metadata
- PodSummary: Simplified pod data for table display
- ContainerMetrics: Resource usage metrics for containers
- MetricsData: Complete metrics data for a pod
- KubernetesEvent: Kubernetes event representation
- WebSocketMessage: WebSocket message structure
- ServerConfig: Server configuration parameters

All models use dataclasses for clean, type-safe data structures with proper
default values and field definitions.

Example:
    ```python
    pod_info = PodInfo(
        name="my-pod",
        namespace="default",
        phase="Running",
        containers=[...]
    )
    ```
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List


@dataclass
class ContainerResource:
    """
    Container resource requests and limits.
    
    Represents the resource specifications for a Kubernetes container,
    including both requests (guaranteed resources) and limits (maximum resources).
    
    Attributes:
        requests: Dictionary of resource requests (e.g., {"cpu": "100m", "memory": "128Mi"})
        limits: Dictionary of resource limits (e.g., {"cpu": "200m", "memory": "256Mi"})
        
    Example:
        ```python
        resources = ContainerResource(
            requests={"cpu": "100m", "memory": "128Mi"},
            limits={"cpu": "200m", "memory": "256Mi"}
        )
        ```
    """
    requests: Dict[str, str] = field(default_factory=dict)
    limits: Dict[str, str] = field(default_factory=dict)


@dataclass
class ContainerEnvVar:
    """
    Container environment variable.
    
    Represents an environment variable in a Kubernetes container,
    including both direct values and references to secrets/configmaps.
    
    Attributes:
        name: Environment variable name
        value: Environment variable value (None for secret/configmap references)
        
    Example:
        ```python
        # Direct value
        env_var = ContainerEnvVar(name="ENV_MODE", value="production")
        
        # Secret reference (value will be None, source shown in UI)
        secret_var = ContainerEnvVar(name="SECRET_TOKEN", value=None)
        ```
    """
    name: str
    value: Optional[str] = None


@dataclass
class ContainerInfo:
    """
    Complete container information.
    
    Represents all relevant information about a Kubernetes container,
    including status, configuration, and resource specifications.
    
    Attributes:
        name: Container name
        ready: Whether the container is ready
        restarts: Number of container restarts
        state: Container state (running, waiting, terminated, etc.)
        image: Container image name and tag
        env: List of environment variables
        resources: Resource requests and limits
        
    Example:
        ```python
        container = ContainerInfo(
            name="app",
            ready=True,
            restarts=0,
            state="running",
            image="myapp:1.2.3",
            env=[ContainerEnvVar(name="ENV_MODE", value="prod")],
            resources=ContainerResource(requests={"cpu": "100m"})
        )
        ```
    """
    name: str
    ready: bool
    restarts: int
    state: str
    image: str
    env: List[ContainerEnvVar] = field(default_factory=list)
    resources: ContainerResource = field(default_factory=ContainerResource)


@dataclass
class PodInfo:
    """
    Complete pod information and metadata.
    
    Represents all relevant information about a Kubernetes pod,
    including status, networking, and container details.
    
    Attributes:
        name: Pod name
        uid: Pod unique identifier
        namespace: Kubernetes namespace
        phase: Pod phase (Running, Pending, Failed, etc.)
        node: Node IP where pod is running
        pod_ip: Pod IP address
        age_seconds: Pod age in seconds since creation
        containers: List of container information
        
    Example:
        ```python
        pod = PodInfo(
            name="api-server-123",
            uid="abc123-def456",
            namespace="default",
            phase="Running",
            node="10.0.0.12",
            pod_ip="10.244.1.23",
            age_seconds=3600,
            containers=[container_info]
        )
        ```
    """
    name: str
    uid: str
    namespace: str
    phase: str
    node: Optional[str] = None
    pod_ip: Optional[str] = None
    age_seconds: int = 0
    containers: List[ContainerInfo] = field(default_factory=list)


@dataclass
class PodSummary:
    """
    Simplified pod data for table display.
    
    Provides a lightweight representation of pod information
    suitable for display in tables and lists.
    
    Attributes:
        name: Pod name
        namespace: Kubernetes namespace
        phase: Pod phase (Running, Pending, Failed, etc.)
        restarts: Total number of container restarts
        ready: Number of ready containers
        total: Total number of containers
        
    Example:
        ```python
        summary = PodSummary(
            name="api-server-123",
            namespace="default",
            phase="Running",
            restarts=0,
            ready=2,
            total=2
        )
        ```
    """
    name: str
    namespace: str
    phase: str
    restarts: int
    ready: int
    total: int


@dataclass
class ContainerMetrics:
    """
    Container resource usage metrics.
    
    Represents real-time resource usage metrics for a container,
    including CPU and memory usage with percentage calculations.
    
    Attributes:
        name: Container name
        cpu_millicores: CPU usage in millicores
        memory_mib: Memory usage in MiB
        cpu_request: CPU request in millicores (if defined)
        cpu_limit: CPU limit in millicores (if defined)
        mem_request_mib: Memory request in MiB (if defined)
        mem_limit_mib: Memory limit in MiB (if defined)
        cpu_pct_of_request: CPU usage as percentage of request
        cpu_pct_of_limit: CPU usage as percentage of limit
        mem_pct_of_request: Memory usage as percentage of request
        mem_pct_of_limit: Memory usage as percentage of limit
        
    Example:
        ```python
        metrics = ContainerMetrics(
            name="app",
            cpu_millicores=125.0,
            memory_mib=128.5,
            cpu_limit=200.0,
            mem_limit_mib=256.0,
            cpu_pct_of_limit=62.5,
            mem_pct_of_limit=50.2
        )
        ```
    """
    name: str
    cpu_millicores: float
    memory_mib: float
    cpu_request: Optional[float] = None
    cpu_limit: Optional[float] = None
    mem_request_mib: Optional[float] = None
    mem_limit_mib: Optional[float] = None
    cpu_pct_of_request: Optional[float] = None
    cpu_pct_of_limit: Optional[float] = None
    mem_pct_of_request: Optional[float] = None
    mem_pct_of_limit: Optional[float] = None


@dataclass
class MetricsData:
    """
    Complete metrics data for a pod.
    
    Contains resource usage metrics for all containers in a pod,
    along with configuration thresholds for alerting.
    
    Attributes:
        containers: List of container metrics
        thresholds: Alert thresholds for resource usage
        disabled: Whether metrics are disabled (metrics server unavailable)
        
    Example:
        ```python
        metrics = MetricsData(
            containers=[container_metrics],
            thresholds={"cpuLimitRed": 90, "memLimitRed": 80},
            disabled=False
        )
        ```
    """
    containers: List[ContainerMetrics] = field(default_factory=list)
    thresholds: Dict[str, int] = field(default_factory=dict)
    disabled: bool = False


@dataclass
class KubernetesEvent:
    """
    Kubernetes event representation.
    
    Represents a Kubernetes event related to a pod or other resource,
    including timing and descriptive information.
    
    Attributes:
        pod: Pod name the event relates to
        event_type: Event type (Normal, Warning, Error)
        reason: Event reason code
        message: Human-readable event message
        age_seconds: Event age in seconds
        target_type: Type of target resource (default: "pod")
        
    Example:
        ```python
        event = KubernetesEvent(
            pod="api-server-123",
            event_type="Warning",
            reason="BackOff",
            message="Back-off restarting failed container",
            age_seconds=120
        )
        ```
    """
    pod: str
    event_type: str
    reason: str
    message: str
    age_seconds: int
    target_type: str = "pod"


@dataclass
class WebSocketMessage:
    """
    WebSocket message structure.
    
    Represents the structure of messages sent over WebSocket connections
    between the Kubeluma server and clients.
    
    Attributes:
        type: Message type (pods, pod, log, metrics, event, etc.)
        data: Optional message data payload
        pod: Optional pod name (for pod-specific messages)
        container: Optional container name (for container-specific messages)
        line: Optional log line content (for log messages)
        
    Example:
        ```python
        # Pod list update message
        message = WebSocketMessage(
            type="pods",
            data={"pods": [...], "focus": "my-pod"}
        )
        
        # Log line message
        log_message = WebSocketMessage(
            type="log",
            pod="my-pod",
            container="app",
            line="2024-01-15 10:30:45 INFO Starting application..."
        )
        ```
    """
    type: str
    data: Optional[Dict[str, Any]] = None
    pod: Optional[str] = None
    container: Optional[str] = None
    line: Optional[str] = None


@dataclass
class ServerConfig:
    """
    Server configuration parameters.
    
    Contains all configuration parameters for the Kubeluma server,
    including network settings, polling intervals, and thresholds.
    
    Attributes:
        host: Server bind host
        port: Server port
        metrics_interval: Metrics polling interval in seconds
        pod_refresh_seconds: Pod refresh interval in seconds
        cpu_limit_red_percent: CPU limit threshold for red highlighting
        mem_limit_red_percent: Memory limit threshold for red highlighting
        log_level: Application log level
        uvicorn_log_level: Uvicorn server log level
        
    Example:
        ```python
        config = ServerConfig(
            host="0.0.0.0",
            port=8080,
            metrics_interval=5.0,
            pod_refresh_seconds=5,
            cpu_limit_red_percent=90,
            mem_limit_red_percent=80,
            log_level="INFO",
            uvicorn_log_level="info"
        )
        ```
    """
    host: str
    port: int
    metrics_interval: float
    pod_refresh_seconds: int
    cpu_limit_red_percent: int
    mem_limit_red_percent: int
    log_level: str
    uvicorn_log_level: str
