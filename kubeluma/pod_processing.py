"""
Pod data processing and transformation utilities.

This module provides functions for processing and transforming Kubernetes pod data
into formats suitable for display in the Kubeluma web interface. It handles
environment variable extraction, resource parsing, and container state processing.

Key Functions:
- extract_container_env_vars: Extract and format environment variables
- extract_container_resources: Parse resource requests and limits
- get_container_state: Determine container state from status
- pod_to_view: Convert Kubernetes pod object to display format

The module handles various Kubernetes resource formats and provides robust
error handling for malformed or missing data.

Example:
    ```python
    pod_view = pod_to_view(k8s_pod_object)
    print(f"Pod {pod_view['name']} has {len(pod_view['containers'])} containers")
    ```
"""

import time
from typing import Dict, Any, List, Optional


def extract_container_env_vars(container_spec: Any) -> List[Dict[str, str]]:
    """Extract environment variables from container spec."""
    env_list = []
    if not container_spec or not getattr(container_spec, 'env', None):
        return env_list
    
    for ev in container_spec.env:
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
    
    return env_list


def extract_container_resources(container_spec: Any) -> Dict[str, Dict[str, str]]:
    """Extract resource requests and limits from container spec."""
    res_req = {}
    res_lim = {}
    
    try:
        if container_spec and getattr(container_spec, 'resources', None):
            rq = getattr(container_spec.resources, 'requests', None) or {}
            lm = getattr(container_spec.resources, 'limits', None) or {}
            for k in ('cpu', 'memory'):
                if rq.get(k):
                    res_req[k] = rq.get(k)
                if lm.get(k):
                    res_lim[k] = lm.get(k)
    except Exception:
        pass
    
    return {'requests': res_req, 'limits': res_lim}


def get_container_state(container_status: Any) -> str:
    """Get container state as a string."""
    if container_status.state.running:
        return 'running'
    elif container_status.state.waiting:
        return f"waiting({container_status.state.waiting.reason})"
    elif container_status.state.terminated:
        return f"terminated({container_status.state.terminated.reason})"
    else:
        return 'unknown'


def pod_to_view(p: Any) -> Dict[str, Any]:
    """Convert Kubernetes pod object to view dictionary."""
    status = p.status
    containers = []
    spec_map = {}
    
    # Build spec map for container lookups
    try:
        for sc in getattr(p.spec, 'containers', []) or []:
            spec_map[sc.name] = sc
    except Exception:
        pass
    
    # Process each container
    for cstat in status.container_statuses or []:
        container_spec = spec_map.get(cstat.name)
        
        # Extract environment variables
        env_list = extract_container_env_vars(container_spec)
        
        # Extract resource information
        resources = extract_container_resources(container_spec)
        
        # Get container state
        state = get_container_state(cstat)
        
        containers.append({
            'name': cstat.name,
            'ready': cstat.ready,
            'restarts': cstat.restart_count,
            'state': state,
            'image': cstat.image,
            'env': env_list,
            'resources': resources
        })
    
    # Calculate pod age
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
