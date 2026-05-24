---
name: device-connect-plugin-driver
description: Playbook for authoring, packaging, and installing Device Connect plugins on device-connect plugin_host devices. Load when the user asks an agent to create a capability, extend a plugin_host, or install service RPCs over device-connect.
---

# device-connect-plugin-driver — agent playbook (plugin authoring)

You are extending a **`plugin_host`** device on [Device Connect](https://github.com/arm/device-connect).
One portal credential exposes **many RPCs**: host management functions plus every loaded plugin.

**Start here on the mesh:** invoke `get_plugin_authoring_guide` on the target `plugin_host`.
That RPC returns this workflow, doc URLs, manifest schema, and install method pointers.

---

## 1. Discover the host

| Step | Action |
|------|--------|
| Fleet summary | `describe_fleet()` or `dc-portalctl devices list` |
| Find plugin hosts | Filter `device_type=plugin_host` |
| Authoring docs on device | `invoke plugin-host-1 get_plugin_authoring_guide {}` |
| Scaffold files | `invoke plugin-host-1 get_plugin_template {"plugin_id": "my-service", "description": "…"}` |
| Examples | `invoke plugin-host-1 list_plugin_examples {}` |

Device **labels** on `plugin_host` include:

- `plugin_driver:authoring_rpc` → `get_plugin_authoring_guide`
- `plugin_driver:template_rpc` → `get_plugin_template`

After `get_device_functions`, look for RPCs tagged with discovery metadata on the host.

---

## 2. Plugin shape (required files)

Each plugin is one directory:

```
my-service/
  manifest.json      # metadata + optional pip deps
  capability.py      # Python class with @rpc methods
```

### manifest.json

```json
{
  "id": "my-service",
  "version": "0.1.0",
  "description": "Controls my upstream API",
  "entry_point": "capability.py",
  "class_name": "MyServiceCapability",
  "dependencies": {
    "python": ["httpx>=0.27"]
  }
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `id` | yes | Folder name; simple slug (`garage-door`, not a path) |
| `class_name` | yes | Python class in entry_point module |
| `entry_point` | yes | Usually `capability.py` |
| `dependencies.python` | no | Declarative; host warns if missing (does not auto-install yet) |

### capability.py

```python
from device_connect_edge.drivers.decorators import rpc, emit, periodic

class MyServiceCapability:
    def __init__(self, device=None):
        self.device = device  # host DeviceRuntime — use for invoke_remote, etc.

    @rpc()
    async def get_service_status(self) -> dict:
        """Health check."""
        return {"status": "ok"}

    @rpc()
    async def run_action(self, action: str = "default") -> dict:
        """Implement service-specific logic here."""
        return {"status": "success", "action": action}
```

**Conventions**

- Use **snake_case** RPC names — they become mesh function names on the host.
- Docstrings on `@rpc` methods become function descriptions in registry / agent-tools.
- Optional lifecycle: `async def start()` / `async def stop()` when loaded/unloaded.
- `@emit()` for events; `@periodic(interval=…)` for background polls (starts after host registers).

**Templates and examples in this repo**

| Path | Use |
|------|-----|
| `src/device_connect_plugin_driver/templates/plugin/` | Canonical scaffold (`get_plugin_template` renders this) |
| `examples/hello-world/` | Smallest working plugin (`hello_world`) |
| `examples/plugin-template/` | Pre-rendered example for `my-service` |
| `capabilities/demo/` | ping + echo reference |

---

## 3. Build a plugin for a specific service

1. **Pick an id** — e.g. `tempest-weather`, `garage-door`, `pool-pump`.
2. **Call `get_plugin_template`** on the host (or copy `examples/plugin-template/`).
3. **Replace stubs** — rename `run_action`; add RPC-sensor-one-RPC or a small action enum.
4. **Map external API** — HTTP, serial, GPIO, etc. inside `@rpc` methods; keep secrets in env on the host, not in the plugin bundle.
5. **Test locally** — `pytest tests/test_hello_world.py` pattern; or install on a dev host with `--no-auto-load`.
6. **Package** — `tar -czf my-service.tgz -C . my-service`
7. **Digest (recommended)** — `shasum -a 256 my-service.tgz`

---

## 4. Install on the plugin_host

All installs are **RPC invokes** on the same device credential.

| Method | RPC | When |
|--------|-----|------|
| Base64 bundle | `install_plugin_from_bundle` | Small plugin; agent embeds archive |
| HTTPS URL | `install_plugin_from_url` | Artifact on CDN / GitHub release |
| Unified manifest | `install_plugin_from_manifest` | `type: python` with `url` or `bundle_b64` |
| Docker sidecar | `install_plugin_from_docker` | Container exposes dc-plugin sidecar HTTP API |
| Local path | `install_plugin` | Files already on device disk |
| Reload only | `load_plugin` | Folder already under host `capabilities_dir` |

Example (base64):

```json
{
  "bundle_b64": "<base64 of my-service.tgz>",
  "digest": "sha256:…"
}
```

Example (URL):

```json
{
  "url": "https://artifacts.example.com/my-service.tgz",
  "digest": "sha256:…"
}
```

Then verify:

```text
list_plugins {}
get_device_functions(plugin-host-1)   # via agent-tools / portal
my_rpc_name {"param": "value"}
```

---

## 5. Docker plugins (same credential)

Use when dependencies conflict or you need isolation. The container runs a **sidecar**; RPCs are **proxied** on the host — not a separate fleet device.

```json
{
  "type": "docker",
  "id": "my-service",
  "image": "registry.example.com/my-service-sidecar:1.0",
  "port": 8787,
  "pull": true,
  "env": {}
}
```

Invoke: `install_plugin_from_docker {"manifest": { … }}`

For a **separate Device Connect device** with its own credential, use **dcd** (`docker_host`) instead.

See `examples/plugin-manifests/README.md`.

---

## 6. Host management RPCs (reference)

| RPC | Purpose |
|-----|---------|
| `get_plugin_authoring_guide` | This playbook as structured JSON + doc URLs |
| `get_plugin_template` | Render manifest + capability.py for a plugin_id |
| `list_plugin_examples` | hello-world, demo, template pointers |
| `list_plugins` | Loaded vs on-disk plugins |
| `load_plugin` / `unload_plugin` / `reload_plugin` | Lifecycle |
| `get_status` | Host config summary |

---

## 7. Security notes for agents

- Installing a plugin is **remote code execution** on the edge host — only do this when the user owns the host and expects it.
- Prefer **digest pinning** (`sha256:…`) on URL/bundle installs.
- Host may enforce `DC_PLUGIN_INSTALL_URL_ALLOWLIST` and `DC_PLUGIN_INSTALL_REQUIRE_DIGEST`.
- Do not embed portal tokens or device JWTs in plugin code.

---

## 8. Repo docs map

| File | Content |
|------|---------|
| [AGENTS.md](AGENTS.md) | This playbook |
| [README.md](README.md) | Install, quick start, RPC table |
| [DESIGN.md](DESIGN.md) | Architecture, harness vs concentrator |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [TODO.md](TODO.md) | Planned work |

Set `DC_PLUGIN_DOCS_BASE_URL` on the host to point agents at your fork or docs site; otherwise defaults are used in `get_plugin_authoring_guide`.
