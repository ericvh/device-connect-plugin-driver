FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "device-connect-edge>=0.2.2" aiohttp pydantic

COPY pyproject.toml README.md ./
COPY src ./src
COPY capabilities ./capabilities

RUN pip install --no-cache-dir .

# Plugin host (default)
ENV DC_PLUGIN_CAPABILITIES_DIR=/app/capabilities
EXPOSE 8787

ENTRYPOINT ["device-connect-plugin-driver"]
CMD ["--capabilities-dir", "/app/capabilities", "--device-id", "plugin-host-edge", "--tenant", "dev"]
