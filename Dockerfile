# Device Connect plugin host — deploy the plugin platform as a container.
# Build:  docker build -t device-connect-plugin-driver .
# Run:    see compose.yaml or README container section

FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Runtime data (mount volumes over these paths in production)
ENV DC_PLUGIN_CAPABILITIES_DIR=/data/capabilities \
    DC_PLUGIN_ARTIFACT_DIR=/data/artifacts \
    DC_PLUGIN_ARTIFACT_HOST=0.0.0.0 \
    DC_PLUGIN_ARTIFACT_PORT=8790

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# Full platform: in-process host + optional Docker sidecar concentrator
RUN pip install ".[concentrator]"

# Bundled reference capability (operators add plugins under /data/capabilities)
COPY capabilities/demo /data/capabilities/demo

RUN groupadd --gid 1000 pluginhost \
    && useradd --uid 1000 --gid pluginhost --create-home --home-dir /home/pluginhost pluginhost \
    && mkdir -p /data/capabilities /data/artifacts /data/creds \
    && chown -R pluginhost:pluginhost /data /data/capabilities

USER pluginhost

VOLUME ["/data/capabilities", "/data/artifacts", "/data/creds"]

# Artifact HTTP server (when DC_PLUGIN_ARTIFACT_SERVE=1 or --artifact-serve)
EXPOSE 8790

# Portal / D2D use outbound connections; no inbound mesh port required by default.

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import device_connect_plugin_driver; print(device_connect_plugin_driver.__version__)" || exit 1

ENTRYPOINT ["device-connect-plugin-driver"]

# Override at deploy time (portal creds, device id, sidecars, artifact serve).
CMD ["--capabilities-dir", "/data/capabilities", "--device-id", "plugin-host-1", "--tenant", "default", "--no-auto-load"]
