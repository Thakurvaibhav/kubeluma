# Kubeluma container image
# Multi-stage for slimmer final runtime
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Build stage installs project
FROM base AS build
# Copy minimal metadata first (better layer cache for deps if they existed)
COPY pyproject.toml README.md /app/
# Copy actual source
COPY kubeluma /app/kubeluma
RUN pip install --upgrade pip && \
    pip install . --no-cache-dir

# Final runtime stage (reuse base so certs present)
FROM base AS runtime
ENV KUBELUMA_PORT=8080 \
    KUBELUMA_HOST=0.0.0.0 \
    KUBELUMA_LOG_LEVEL=INFO
WORKDIR /app

# Copy installed site-packages + entrypoints
COPY --from=build /usr/local /usr/local

# Create non-root user with home (for mounted kubeconfig)
RUN useradd -u 10001 -m -r -s /usr/sbin/nologin kubeluma \
 && install -d -o kubeluma -g kubeluma /home/kubeluma/.kube \
 && chown -R kubeluma:kubeluma /app
USER kubeluma

EXPOSE 8080

ENTRYPOINT ["kubeluma", "serve"]
# Example:
# docker run -p 8080:8080 -v ~/.kube:/home/kubeluma/.kube:ro \
#   -e KUBECONFIG=/home/kubeluma/.kube/config kubeluma:local
