"""
Metrics processing and transformation utilities.

This module provides functions for processing and transforming Kubernetes metrics data
into formats suitable for display in the Kubeluma web interface. It handles CPU and
memory value parsing, percentage calculations, and resource threshold comparisons.

Key Functions:
- parse_cpu_value: Parse CPU values from Kubernetes format to millicores
- parse_memory_value: Parse memory values from Kubernetes format to MiB
- calculate_resource_percentages: Calculate usage percentages vs requests/limits
- process_container_metrics: Process metrics for a single container
- metrics_to_view: Convert Kubernetes metrics to display format

The module handles various Kubernetes resource formats (n, m, Ki, Mi, Gi, Ti) and
provides accurate percentage calculations for resource utilization monitoring.

Example:
    ```python
    metrics_view = metrics_to_view(k8s_metrics_object, pod_view)
    for container in metrics_view['containers']:
        print(f"CPU usage: {container['cpuPctOfLimit']}% of limit")
    ```
"""

from typing import Dict, Any, Optional, List
from .constants import DEFAULT_CPU_LIMIT_RED_PERCENT, DEFAULT_MEM_LIMIT_RED_PERCENT


def parse_cpu_value(value: str) -> float:
    """Parse CPU value from Kubernetes format to millicores."""
    try:
        if value.endswith('n'):
            return int(value[:-1]) / 1_000_000  # n -> m
        if value.endswith('m'):
            return int(value[:-1])
        return float(value) * 1000  # cores -> m
    except Exception:
        return 0


def parse_memory_value(value: str) -> float:
    """Parse memory value from Kubernetes format to MiB."""
    try:
        if value.endswith('Ki'):
            return round(int(value[:-2]) / 1024, 2)
        if value.endswith('Mi'):
            return float(value[:-2])
        if value.endswith('Gi'):
            return float(value[:-2]) * 1024
        if value.endswith('Ti'):
            return float(value[:-2]) * 1024 * 1024
        return 0.0
    except Exception:
        return 0.0


def calculate_resource_percentages(
    usage: float, 
    request: Optional[float], 
    limit: Optional[float]
) -> tuple[Optional[float], Optional[float]]:
    """Calculate percentage of request and limit for a resource."""
    pct_request = None
    pct_limit = None
    
    if request and request > 0:
        pct_request = round((usage / request) * 100, 1)
    
    if limit and limit > 0:
        pct_limit = round((usage / limit) * 100, 1)
    
    return pct_request, pct_limit


def process_container_metrics(
    container_data: Dict[str, Any], 
    resource_map: Dict[str, Dict[str, Dict[str, str]]]
) -> Dict[str, Any]:
    """Process metrics for a single container."""
    name = container_data['name']
    usage = container_data.get('usage', {})
    
    cpu_raw = usage.get('cpu', '0')
    mem_raw = usage.get('memory', '0')
    
    cpu_m = parse_cpu_value(cpu_raw)
    mem_mib = parse_memory_value(mem_raw)
    
    # Get resource requests and limits
    req_cpu = lim_cpu = req_mem = lim_mem = None
    pct_cpu_req = pct_cpu_lim = pct_mem_req = pct_mem_lim = None
    
    if name in resource_map:
        rq = (resource_map[name].get('requests') or {})
        lm = (resource_map[name].get('limits') or {})
        
        if 'cpu' in rq:
            req_cpu = parse_cpu_value(rq['cpu'])
            pct_cpu_req, _ = calculate_resource_percentages(cpu_m, req_cpu, None)
        
        if 'cpu' in lm:
            lim_cpu = parse_cpu_value(lm['cpu'])
            _, pct_cpu_lim = calculate_resource_percentages(cpu_m, None, lim_cpu)
        
        if 'memory' in rq:
            req_mem = parse_memory_value(rq['memory'])
            pct_mem_req, _ = calculate_resource_percentages(mem_mib, req_mem, None)
        
        if 'memory' in lm:
            lim_mem = parse_memory_value(lm['memory'])
            _, pct_mem_lim = calculate_resource_percentages(mem_mib, None, lim_mem)
    
    return {
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
    }


def metrics_to_view(m: Dict[str, Any], pod_view: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Convert Kubernetes metrics to view format with percentage calculations."""
    # Build resource map {container: {'requests':..., 'limits':...}}
    res_map = {}
    if pod_view:
        for c in pod_view.get('containers', []):
            res_map[c['name']] = c.get('resources') or {}
    
    containers = []
    for c in m.get('containers', []):
        container_metrics = process_container_metrics(c, res_map)
        containers.append(container_metrics)
    
    return {
        'containers': containers, 
        'thresholds': {
            'cpuLimitRed': DEFAULT_CPU_LIMIT_RED_PERCENT, 
            'memLimitRed': DEFAULT_MEM_LIMIT_RED_PERCENT
        }
    }
