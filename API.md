# Kubeluma API Documentation

## Overview

Kubeluma provides both a REST API and WebSocket interface for real-time Kubernetes pod monitoring and debugging. This document describes all available endpoints, message formats, and usage examples.

## Table of Contents

- [REST API Endpoints](#rest-api-endpoints)
- [WebSocket API](#websocket-api)
- [Data Models](#data-models)
- [Error Handling](#error-handling)
- [Examples](#examples)

## REST API Endpoints

### Base URL

All REST endpoints are available at the server's base URL (default: `http://localhost:8080`).

### Endpoints

#### GET /

**Description**: Serves the main web interface.

**Response**: HTML page with the Kubeluma web UI.

**Example**:
```bash
curl http://localhost:8080/
```

#### POST /api/set_pattern

**Description**: Set the pod name regex pattern for filtering.

**Request Body**:
```json
{
  "pattern": "^api-"
}
```

**Response**:
```json
{
  "ok": true,
  "pattern": "^api-"
}
```

**Error Response**:
```json
{
  "detail": "Invalid regex pattern: [unterminated character set"
}
```

**Example**:
```bash
curl -X POST http://localhost:8080/api/set_pattern \
  -H "Content-Type: application/json" \
  -d '{"pattern": "^api-"}'
```

#### POST /api/reset_pattern

**Description**: Clear the current pod pattern and reset to interactive mode.

**Response**:
```json
{
  "ok": true
}
```

**Example**:
```bash
curl -X POST http://localhost:8080/api/reset_pattern
```

#### GET /api/current_pattern

**Description**: Get the current pod pattern.

**Response**:
```json
{
  "pattern": "^api-"
}
```

**Example**:
```bash
curl http://localhost:8080/api/current_pattern
```

## WebSocket API

### Connection

**URL**: `ws://localhost:8080/ws`

**Protocol**: WebSocket

**Authentication**: None (currently)

### Message Format

All WebSocket messages use JSON format.

### Client → Server Messages

#### Subscribe to Pod Updates

```json
{
  "action": "subscribe",
  "channel": "pod"
}
```

#### Subscribe to Container Logs

```json
{
  "action": "subscribe",
  "channel": "logs",
  "pod": "my-pod",
  "container": "app"
}
```

#### Focus on Specific Pod

```json
{
  "action": "focus",
  "pod": "my-pod"
}
```

### Server → Client Messages

#### Awaiting Pattern

Sent when no pod pattern is set and the UI should show the pattern input overlay.

```json
{
  "type": "awaitingPattern"
}
```

#### Pod List Update

Sent when the list of matching pods changes.

```json
{
  "type": "pods",
  "data": {
    "pods": [
      {
        "name": "api-server-123",
        "namespace": "default",
        "phase": "Running",
        "restarts": 0,
        "ready": 1,
        "total": 1
      }
    ],
    "focus": "api-server-123",
    "pattern": "^api-"
  }
}
```

#### Pod Details Update

Sent when detailed information about the focused pod changes.

```json
{
  "type": "pod",
  "data": {
    "name": "api-server-123",
    "uid": "abc123-def456-ghi789",
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
        "image": "myapp:1.2.3",
        "env": [
          {
            "name": "ENV_MODE",
            "value": "production"
          },
          {
            "name": "SECRET_TOKEN",
            "value": "*** (secret mysecret/token)"
          }
        ],
        "resources": {
          "requests": {
            "cpu": "100m",
            "memory": "128Mi"
          },
          "limits": {
            "cpu": "200m",
            "memory": "256Mi"
          }
        }
      }
    ]
  }
}
```

#### Log Line

Sent for each new log line from a subscribed container.

```json
{
  "type": "log",
  "pod": "api-server-123",
  "container": "app",
  "line": "2024-01-15 10:30:45 INFO Starting application..."
}
```

#### Metrics Update

Sent periodically with resource usage metrics for the focused pod.

```json
{
  "type": "metrics",
  "data": {
    "containers": [
      {
        "name": "app",
        "cpu": 12.5,
        "memoryMiB": 34.5,
        "cpuRequest": 100.0,
        "cpuLimit": 200.0,
        "memRequestMiB": 128.0,
        "memLimitMiB": 256.0,
        "cpuPctOfRequest": 12.5,
        "cpuPctOfLimit": 6.25,
        "memPctOfRequest": 27.0,
        "memPctOfLimit": 13.5
      }
    ],
    "thresholds": {
      "cpuLimitRed": 90,
      "memLimitRed": 80
    }
  }
}
```

#### Metrics Disabled

Sent when metrics server is not available.

```json
{
  "type": "metrics",
  "data": {
    "disabled": true
  }
}
```

#### Kubernetes Event

Sent when a new Kubernetes event occurs for the focused pod.

```json
{
  "type": "event",
  "data": {
    "pod": "api-server-123",
    "type": "Warning",
    "reason": "BackOff",
    "message": "Back-off restarting failed container",
    "ageSeconds": 120,
    "targetType": "pod"
  }
}
```

## Data Models

### Pod Summary

```typescript
interface PodSummary {
  name: string;
  namespace: string;
  phase: string;
  restarts: number;
  ready: number;
  total: number;
}
```

### Pod Details

```typescript
interface PodDetails {
  name: string;
  uid: string;
  namespace: string;
  phase: string;
  node?: string;
  podIP?: string;
  ageSeconds: number;
  containers: ContainerInfo[];
}

interface ContainerInfo {
  name: string;
  ready: boolean;
  restarts: number;
  state: string;
  image: string;
  env: EnvironmentVariable[];
  resources: ResourceSpec;
}

interface EnvironmentVariable {
  name: string;
  value?: string;
}

interface ResourceSpec {
  requests: Record<string, string>;
  limits: Record<string, string>;
}
```

### Metrics Data

```typescript
interface MetricsData {
  containers: ContainerMetrics[];
  thresholds: {
    cpuLimitRed: number;
    memLimitRed: number;
  };
  disabled?: boolean;
}

interface ContainerMetrics {
  name: string;
  cpu: number; // millicores
  memoryMiB: number;
  cpuRequest?: number;
  cpuLimit?: number;
  memRequestMiB?: number;
  memLimitMiB?: number;
  cpuPctOfRequest?: number;
  cpuPctOfLimit?: number;
  memPctOfRequest?: number;
  memPctOfLimit?: number;
}
```

### Kubernetes Event

```typescript
interface KubernetesEvent {
  pod: string;
  type: string;
  reason: string;
  message: string;
  ageSeconds: number;
  targetType: string;
}
```

## Error Handling

### HTTP Status Codes

- `200 OK`: Successful request
- `400 Bad Request`: Invalid request data (e.g., invalid regex pattern)
- `500 Internal Server Error`: Server error

### WebSocket Errors

WebSocket errors are typically handled by closing the connection. The client should implement reconnection logic.

### Common Error Scenarios

1. **Invalid Regex Pattern**: Returns 400 with error details
2. **Kubernetes Connection Error**: Server logs error, may affect functionality
3. **Metrics Server Unavailable**: Metrics data will show as disabled
4. **Pod Not Found**: Returns empty pod list or None for individual pod requests

## Examples

### Complete WebSocket Client Example

```javascript
const ws = new WebSocket('ws://localhost:8080/ws');

ws.onopen = () => {
  console.log('Connected to Kubeluma');
  
  // Subscribe to pod updates
  ws.send(JSON.stringify({
    action: 'subscribe',
    channel: 'pod'
  }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  switch (message.type) {
    case 'awaitingPattern':
      console.log('Please set a pod pattern');
      break;
      
    case 'pods':
      console.log('Pod list updated:', message.data.pods);
      break;
      
    case 'pod':
      console.log('Pod details:', message.data);
      break;
      
    case 'log':
      console.log(`[${message.pod}:${message.container}] ${message.line}`);
      break;
      
    case 'metrics':
      if (message.data.disabled) {
        console.log('Metrics not available');
      } else {
        console.log('Metrics:', message.data.containers);
      }
      break;
      
    case 'event':
      console.log('Kubernetes event:', message.data);
      break;
  }
};

// Focus on a specific pod
function focusPod(podName) {
  ws.send(JSON.stringify({
    action: 'focus',
    pod: podName
  }));
}

// Subscribe to container logs
function subscribeToLogs(podName, containerName) {
  ws.send(JSON.stringify({
    action: 'subscribe',
    channel: 'logs',
    pod: podName,
    container: containerName
  }));
}
```

### Python Client Example

```python
import asyncio
import websockets
import json

async def kubeluma_client():
    uri = "ws://localhost:8080/ws"
    
    async with websockets.connect(uri) as websocket:
        # Subscribe to pod updates
        await websocket.send(json.dumps({
            "action": "subscribe",
            "channel": "pod"
        }))
        
        # Listen for messages
        async for message in websocket:
            data = json.loads(message)
            
            if data["type"] == "pods":
                print(f"Found {len(data['data']['pods'])} pods")
                for pod in data["data"]["pods"]:
                    print(f"  - {pod['name']} ({pod['phase']})")
            
            elif data["type"] == "log":
                print(f"[{data['pod']}:{data['container']}] {data['line']}")

# Run the client
asyncio.run(kubeluma_client())
```

### Setting Pod Pattern via API

```bash
# Set pattern to match all pods starting with "api"
curl -X POST http://localhost:8080/api/set_pattern \
  -H "Content-Type: application/json" \
  -d '{"pattern": "^api"}'

# Set pattern to match pods containing "web"
curl -X POST http://localhost:8080/api/set_pattern \
  -H "Content-Type: application/json" \
  -d '{"pattern": "web"}'

# Reset to interactive mode
curl -X POST http://localhost:8080/api/reset_pattern
```

## Configuration

### Environment Variables

- `KUBELUMA_HOST`: Server host (default: localhost)
- `KUBELUMA_PORT`: Server port (default: 8080)
- `KUBELUMA_POD_REFRESH_SEC`: Pod refresh interval in seconds (default: 5)
- `KUBELUMA_CPU_LIMIT_RED_PCT`: CPU limit threshold for red highlighting (default: 90)
- `KUBELUMA_MEM_LIMIT_RED_PCT`: Memory limit threshold for red highlighting (default: 80)
- `KUBELUMA_LOG_LEVEL`: Application log level (default: INFO)
- `KUBELUMA_UVICORN_LEVEL`: Uvicorn log level (default: info)

### Command Line Options

```bash
kubeluma serve [OPTIONS]

Options:
  --pod TEXT              Regex pattern to match pod names
  --namespace TEXT        Namespace to watch (default: all)
  --kubeconfig TEXT       Path to kubeconfig file
  --context TEXT          Kubernetes context to use
  --host TEXT             Host to bind to
  --port INTEGER          Port to bind to
  --no-open               Don't open browser automatically
  --metrics-interval FLOAT Metrics poll interval in seconds
```

## Rate Limits and Performance

- Pod list is refreshed every 5 seconds by default
- Metrics are polled every 5 seconds by default
- Events are polled every 6 seconds
- Log streaming is real-time with 200 line tail
- Maximum 5000 events are kept in memory
- WebSocket connections are cleaned up automatically

## Security Considerations

- No authentication is currently implemented
- All data is transmitted in plain text over WebSocket
- Secrets in environment variables are masked in the UI
- Consider using HTTPS/WSS in production environments
- Ensure proper network security for Kubernetes API access
