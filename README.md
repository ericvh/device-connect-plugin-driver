# device-connect-plugin-driver — Device Connect plugin enabler

**device-connect-plugin-driver** is a [Device Connect](https://github.com/arm/device-connect) driver that turns one mesh identity into a **plugin host**: load Python capability modules at runtime and expose their RPCs through **the same portal credential** — on **Zenoh D2D** or **Portal/NATS**.

License: [Apache-2.0](LICENSE)

## Documentation

| Doc | Purpose |
|-----|---------|
| [README.md](README.md) | Install, quick start, RPC reference |
| [AGENTS.md](AGENTS.md) | **Agent playbook** — scaffold, package, and install plugins |
| [DESIGN.md](DESIGN.md) | Architecture, credential model, harness vs concentrator |
| [TODO.md](TODO.md) | Planned work and open items |
| [SECURITY.md](SECURITY.md) | Threat model and hardening |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

## Does existing device-connect support this?

**Partially — the primitives exist; the harness did not.**

| Piece | Status in device-connect |
|-------|--------------------------|
| In-process capability loader (`CapabilityDriverMixin`) | Implemented in `device-connect-edge` |
| `@rpc` / `@emit` / `@periodic` on loaded classes | Supported |
| One JWT → one `device_id` → many RPCs | Supported (functions merge into one driver) |
| Remote "load plugin" over mesh | **Not built-in** — this driver adds `load_plugin` / `unload_plugin` RPCs |
| Hot refresh in registry / D2D presence | **Gap** — the driver calls `_register(force=True)` or D2D burst after load |
| Sub-devices as separate fleet rows on one cred | **Not supported** — one credential = one device identity |
| Portal upload of plugin artifacts | **Not supported** — install from disk (`install_plugin`) or sidecar deploy |

Waggle/Sage plugins (`sage.yaml`, `waggle.plugin`) are a **different** packaging model. the driver uses Device Connect `manifest.json` + Python entry points (see `capabilities/demo/`).

## Python harness vs concentrator?

**Use both, for different jobs:**

| Approach | When | Credential model |
|----------|------|------------------|
| **In-process (default)** | Lightweight RPCs, shared Python env, fastest iteration | One `plugin_host` device |
| **Sidecar concentrator** | Isolation, conflicting deps, privileged hardware | Still **one** host credential; sidecars are local HTTP proxies |
| **dcd / separate containers** | Full stack isolation, distinct lifecycle | **Separate** portal provision per container if each must appear as its own device |

this driver implements the first two. For fleet-visible sub-devices each needing their own ACL, provision additional portal devices (or use [dcd](https://github.com/...) to run them).

See [DESIGN.md](DESIGN.md) for the full decision record. Planned work is tracked in [TODO.md](TODO.md).

## Install

```bash
cd ~/src/device-connect-plugin-driver
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Optional Docker sidecar support
pip install -e ".[dev,concentrator]"
```

Requires Python **3.12** or **3.13** and `device-connect-edge` (from PyPI or a local editable install of `~/src/device-connect`).

## Quick start — D2D (Zenoh LAN)

```bash
export DEVICE_CONNECT_ALLOW_INSECURE=true
device-connect-plugin-driver \
  --allow-insecure \
  --device-id plugin-host-1 \
  --tenant dev \
  --capabilities-dir ./capabilities
```

The bundled `demo` capability exposes `ping` and `echo` on the host device.

For a minimal plugin-addition smoke test, use [examples/hello-world/](examples/hello-world/) — a single `hello_world` RPC. See that directory's README for step-by-step D2D and portal flows.

## Quick start — Portal

Provision one device in the portal, then:

```bash
device-connect-plugin-driver \
  --portal \
  --portal-credentials ~/.config/device-connect/my-plugin-host.creds.json \
  --nats-credentials-file ~/.config/device-connect/my-plugin-host.creds.json
```

Agents discover functions via portal / `dc-portalctl` as usual. After loading a plugin remotely:

```bash
# From an agent or another device with invoke access
invoke plugin-host-1 load_plugin '{"plugin_id": "demo"}'
# Registry capabilities refresh automatically (infra) or D2D presence bursts (LAN)
```

## Plugin layout

Each plugin is a directory under `capabilities/`:

```
capabilities/
  my-sensor/
    manifest.json      # id, class_name, entry_point, optional dependencies
    capability.py      # class with @rpc methods
```

Example manifest:

```json
{
  "id": "my-sensor",
  "version": "0.1.0",
  "description": "Reads a sensor",
  "entry_point": "capability.py",
  "class_name": "MySensorCapability",
  "dependencies": {
    "python": ["pyserial>=3.5"]
  }
}
```

## Host RPCs

| RPC | Description |
|-----|-------------|
| `get_plugin_authoring_guide` | Structured playbook + doc URLs (call first) |
| `get_plugin_template` | Render manifest + capability.py for a plugin_id |
| `list_plugin_examples` | Pointers to hello-world, demo, template |
| `get_status` | Host config and loaded plugin count |
| `list_plugins` | Loaded + on-disk capabilities |
| `load_plugin` | Load by folder name |
| `unload_plugin` | Unload a running plugin |
| `reload_plugin` | Unload + load (pick up code changes) |
| `install_plugin` | Copy a folder into `capabilities_dir` and load |
| `install_plugin_from_url` | Download `.tar.gz` / `.zip` from HTTPS, verify digest, install |
| `install_plugin_from_bundle` | Install from base64-encoded archive |
| `install_plugin_from_docker` | Deploy container from docker manifest (sidecar, proxied on host) |
| `install_plugin_from_manifest` | Unified entry — `type: python` (url/bundle) or `type: docker` |
| `deploy_sidecar` | Run plugin in Docker sidecar from local capability dir (requires `[concentrator]`) |
| `undeploy_sidecar` | Stop sidecar and remove proxied RPCs |

Plus any RPCs from loaded capabilities (e.g. `hello_world`, `demo.ping`, `ping`).

## Hello-world example

Copy or install the example plugin, then load and invoke:

```bash
# Option A: copy into capabilities dir before starting the host
cp -R examples/hello-world capabilities/

# Option B: install at runtime (host already running)
# invoke install_plugin {"source_path": "/path/to/device-connect-plugin-driver/examples/hello-world"}

# After load_plugin {"plugin_id": "hello-world"}:
# invoke hello_world {"name": "plugin"}
# → {"message": "Hello, plugin!"}
```

Local test without a mesh: `pytest tests/test_hello_world.py`

## Remote plugin delivery (agents)

Agents with `devices:invoke` can install plugins without SSH:

```bash
# Package a capability folder
tar -czf hello-world.tgz -C examples hello-world
DIGEST="sha256:$(shasum -a 256 hello-world.tgz | awk '{print $1}')"

# Option 1: base64 bundle (small plugins)
B64=$(base64 < hello-world.tgz)
install_plugin_from_bundle {"bundle_b64": "<b64>", "digest": "$DIGEST"}

# Option 2: HTTPS URL (host artifact on your CDN/GitHub releases)
install_plugin_from_url {"url": "https://…/hello-world.tgz", "digest": "$DIGEST"}

# Option 3: docker sidecar manifest (see examples/plugin-manifests/)
install_plugin_from_docker {"manifest": {"type": "docker", "id": "hello-sidecar", "image": "…", "port": 8787}}

# Unified manifest dispatcher
install_plugin_from_manifest {"manifest": {"type": "python", "url": "https://…", "digest": "$DIGEST"}}
```

Host env knobs:

- `DC_PLUGIN_INSTALL_URL_ALLOWLIST` — comma-separated allowed URL hosts
- `DC_PLUGIN_INSTALL_REQUIRE_DIGEST=1` — reject installs without matching digest
- `DC_PLUGIN_MAX_PLUGIN_BYTES` — max download/bundle size (default 10 MiB)

See [examples/plugin-manifests/README.md](examples/plugin-manifests/README.md).

## Container deployment

Images are built on every push to `main` and published to GitHub Container Registry (see [.github/workflows/docker.yml](.github/workflows/docker.yml)).

| Image | Dockerfile | Purpose |
|-------|------------|---------|
| `ghcr.io/ericvh/device-connect-plugin-driver` | [Dockerfile](Dockerfile) | Plugin host (in-process + optional sidecar concentrator) |
| `ghcr.io/ericvh/dc-plugin-sidecar` | [Dockerfile.sidecar](Dockerfile.sidecar) | Single-capability HTTP sidecar |

**Pull and run (D2D dev):**

```bash
docker pull ghcr.io/ericvh/device-connect-plugin-driver:latest

docker run --rm -it \
  -e DEVICE_CONNECT_ALLOW_INSECURE=true \
  -v plugin-caps:/data/capabilities \
  -v plugin-artifacts:/data/artifacts \
  -p 8790:8790 \
  ghcr.io/ericvh/device-connect-plugin-driver:latest \
  --allow-insecure \
  --device-id plugin-host-1 \
  --tenant dev \
  --capabilities-dir /data/capabilities \
  --no-auto-load
```

**Portal mode** — mount provisioned credentials:

```bash
docker run --rm -it \
  -v $HOME/.config/device-connect/plugin-host.creds.json:/data/creds/host.creds.json:ro \
  -v plugin-caps:/data/capabilities \
  ghcr.io/ericvh/device-connect-plugin-driver:latest \
  --portal \
  --portal-credentials /data/creds/host.creds.json \
  --capabilities-dir /data/capabilities
```

**Compose** (local build or pull):

```bash
docker compose up --build
# Sidecar concentrator mode (Docker socket required):
docker compose --profile sidecars up plugin-host-sidecars
```

Persistent volumes: `/data/capabilities` (plugins), `/data/artifacts` (local artifact store), `/data/creds` (portal `.creds.json`).

## Portal provisioning

```bash
./examples/portal-provision.sh plugin-host-001 erivan01
```

See [docs/PUBLISHING.md](docs/PUBLISHING.md) for PyPI release steps.

## Agent discoverability (mesh)

`plugin_host` devices advertise **labels** on registration:

- `plugin_driver:authoring_rpc` → `get_plugin_authoring_guide`
- `plugin_driver:template_rpc` → `get_plugin_template`

Agents should call these RPCs before authoring a plugin:

```text
get_plugin_authoring_guide {}   # workflow, schema, doc URLs, install methods
get_plugin_template {"plugin_id": "my-service", "description": "…"}
list_plugin_examples {}
```

`get_status` also includes an `authoring` block with RPC names. Full playbook: [AGENTS.md](AGENTS.md).

**Templates:** `src/device-connect-plugin-driver/templates/plugin/` (rendered by `get_plugin_template`) · **Example:** [examples/plugin-template/](examples/plugin-template/) · **Minimal:** [examples/hello-world/](examples/hello-world/)

## Sidecar / concentrator mode

For plugins that need isolation:

```bash
pip install -e ".[concentrator]"
docker build -f Dockerfile.sidecar -t dc-plugin-sidecar:local .

device-connect-plugin-driver --enable-sidecars --capabilities-dir ./capabilities ...
# Then invoke deploy_sidecar {"plugin_id": "demo"}
```

Sidecars speak HTTP locally; the host proxies their functions onto the mesh identity.

## Development

```bash
pytest
ruff check src tests
```

## Related projects

- [device-connect](https://github.com/arm/device-connect) — core mesh + `CapabilityDriverMixin`
- [dcd](https://github.com/) — Docker host driver (container provisioning, separate device per workload)
- [lerobot-device-connect](https://github.com/) — reference portal launcher pattern
