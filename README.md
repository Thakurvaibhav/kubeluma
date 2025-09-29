# Kubeluma

**Real-time Kubernetes Pod Inspection Tool**

Kubeluma is a modern, web-based tool for real-time monitoring and debugging of Kubernetes pods. It provides a zero-dependency frontend with live log streaming, resource metrics, event monitoring, and environment variable inspection.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-TBD-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-available-blue.svg)](Dockerfile)

## ✨ Features

- **🔍 Real-time Pod Discovery**: Filter pods using regex patterns
- **📊 Live Metrics**: CPU and memory usage with percentage calculations vs requests/limits
- **📝 Log Streaming**: Real-time container log streaming with pause/resume
- **📋 Event Monitoring**: Kubernetes events filtered per focused pod
- **🔧 Environment Variables**: Inspect container environment variables (secrets masked)
- **⚡ WebSocket Updates**: Real-time updates via WebSocket connections
- **🎨 Modern UI**: Dark theme with responsive design
- **🐳 Docker Ready**: Containerized deployment with multi-stage builds
- **🔒 Security**: Non-root container user and proper secret masking

## 🚀 Quick Start

### Installation

```bash
# Install from source
git clone https://github.com/your-org/kubeluma.git
cd kubeluma
pip install -e .

# Or use Docker
docker build -t kubeluma:latest .
```

### Basic Usage

```bash
# Interactive mode - enter pod pattern in web UI
kubeluma serve

# Pre-configured mode - specify pattern via CLI
kubeluma serve --pod '^api-'

# Specific namespace
kubeluma serve --pod '^web-' --namespace prod

# Custom port and host
kubeluma serve --host 0.0.0.0 --port 8080
```

### Docker Usage

```bash
# Run with default settings
docker run --rm -p 8080:8080 \
  -v ~/.kube:/home/kubeluma/.kube:ro \
  -e KUBECONFIG=/home/kubeluma/.kube/config \
  kubeluma:latest

# Run with pre-configured pattern
docker run --rm -p 8080:8080 \
  -v ~/.kube:/home/kubeluma/.kube:ro \
  kubeluma:latest kubeluma serve --pod '^api-' --namespace prod
```

## 📖 Documentation

- **[API Documentation](API.md)** - Complete REST API and WebSocket documentation
- **[Configuration](#configuration)** - Environment variables and settings
- **[Development](#development)** - Building and contributing
- **[Troubleshooting](#troubleshooting)** - Common issues and solutions

## 🎯 How It Works

1. **Pod Discovery**: Enter a regex pattern to filter pods (e.g., `^api-` for all pods starting with "api")
2. **Real-time Updates**: WebSocket connection provides live updates for pod status, logs, and metrics
3. **Focus Management**: Click on any pod to focus and view detailed information
4. **Log Streaming**: Subscribe to container logs with real-time streaming
5. **Metrics Monitoring**: View CPU and memory usage with percentage calculations vs requests/limits
6. **Event Tracking**: Monitor Kubernetes events filtered per focused pod

## ⚙️ Configuration

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--pod` | Pod name regex pattern | Interactive input |
| `--namespace` | Namespace filter | All namespaces |
| `--kubeconfig` | Path to kubeconfig file | Standard loading |
| `--context` | Kubernetes context | Current context |
| `--host` | Server bind host | localhost |
| `--port` | Server port | 8080 |
| `--no-open` | Don't auto-open browser | Auto-open |
| `--metrics-interval` | Metrics poll interval (seconds) | 5.0 |

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `KUBELUMA_HOST` | Server bind host | localhost |
| `KUBELUMA_PORT` | Server port | 8080 |
| `KUBELUMA_POD_REFRESH_SEC` | Pod refresh interval | 5 |
| `KUBELUMA_CPU_LIMIT_RED_PCT` | CPU limit threshold for red highlighting | 90 |
| `KUBELUMA_MEM_LIMIT_RED_PCT` | Memory limit threshold for red highlighting | 80 |
| `KUBELUMA_LOG_LEVEL` | Application log level | INFO |
| `KUBELUMA_UVICORN_LEVEL` | Uvicorn log level | info |

## 🔧 Development

### Prerequisites

- Python 3.10+
- Kubernetes cluster access
- Docker (optional)

### Setup

```bash
# Clone the repository
git clone https://github.com/your-org/kubeluma.git
cd kubeluma

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# Run in development mode
kubeluma serve --pod '^test-'
```

### Project Structure

```
kubeluma/
├── kubeluma/           # Main package
│   ├── __init__.py     # Package initialization
│   ├── cli.py          # Command-line interface
│   ├── server.py       # FastAPI server and WebSocket handling
│   ├── kube.py         # Kubernetes client interactions
│   ├── constants.py    # Configuration constants
│   ├── exceptions.py   # Custom exceptions
│   ├── validation.py   # Input validation
│   ├── models.py       # Data models
│   ├── pod_processing.py    # Pod data processing
│   ├── metrics_processing.py # Metrics processing
│   └── index.html      # Web UI
├── pyproject.toml      # Project configuration
├── Dockerfile          # Container configuration
├── README.md           # This file
└── API.md              # API documentation
```

## 🐛 Troubleshooting

### Common Issues

#### "Failed to connect to Kubernetes"
- Ensure your kubeconfig is properly configured
- Check that you have access to the cluster
- Verify the context is correct: `kubectl config current-context`

#### "Metrics not available"
- Install metrics-server in your cluster
- Check if metrics-server is running: `kubectl get pods -n kube-system | grep metrics`

#### "No pods found"
- Verify your regex pattern is correct
- Check if pods exist in the specified namespace
- Ensure you have permissions to list pods

#### WebSocket connection issues
- Check firewall settings
- Verify the server is accessible from your browser
- Check browser console for WebSocket errors

### Debug Mode

```bash
# Enable debug logging
export KUBELUMA_LOG_LEVEL=DEBUG
kubeluma serve --pod '^test-'
```

### Performance Tuning

```bash
# Increase refresh intervals for better performance
export KUBELUMA_POD_REFRESH_SEC=10
export KUBELUMA_METRICS_INTERVAL=10
kubeluma serve
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

### Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Add tests if applicable
5. Commit your changes: `git commit -m 'Add amazing feature'`
6. Push to the branch: `git push origin feature/amazing-feature`
7. Open a Pull Request

### Code Style

- Follow PEP 8 style guidelines
- Use type hints for all functions
- Add docstrings for all public functions and classes
- Run linting before submitting: `flake8 kubeluma/`

## 📋 Roadmap

- [ ] Multi-pod focused metrics aggregate view
- [ ] Sort by highest CPU / memory usage
- [ ] Download logs functionality
- [ ] Pod describe dump panel
- [ ] RBAC error surfacing for events/metrics
- [ ] Authentication and authorization
- [ ] Prometheus metrics integration
- [ ] Custom dashboard themes
- [ ] Export functionality for pod data

## 📄 License

This project is licensed under the TBD License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/) for the web framework
- Uses [Kubernetes Python Client](https://github.com/kubernetes-client/python) for cluster interactions
- Inspired by the need for better Kubernetes debugging tools

## 📞 Support

- 📖 [Documentation](API.md)
- 🐛 [Issue Tracker](https://github.com/your-org/kubeluma/issues)
- 💬 [Discussions](https://github.com/your-org/kubeluma/discussions)

---

**Made with ❤️ for the Kubernetes community**
