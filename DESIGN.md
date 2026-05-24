# device-connect-plugin-driver design — plugin enabler for Device Connect

See also: [README.md](README.md) · [AGENTS.md](AGENTS.md) · [TODO.md](TODO.md) · [CHANGELOG.md](CHANGELOG.md)

## Problem

You want to extend an edge device **after** it is commissioned: new RPCs and behaviors should appear on the mesh **without issuing a new portal credential**, whether the device uses **Zenoh D2D** or **Portal/NATS**.

## What device-connect already provides

### Capability loader (in-process)

`device-connect-edge` ships `CapabilityDriverMixin` and `CapabilityLoader`:

- Scan `capabilities/<id>/manifest.json`
- Dynamic import of `entry_point` module
- Wire `@rpc`, `@emit`, `@periodic` into the host driver
- `load_capability` / `unload_capability` with cache invalidation

This is the right **foundation** for a plugin enabler.

### What it does not provide

1. **No reference host driver** — mixin exists but no production driver used `load_capabilities()` in-tree at time of writing.
2. **No remote load API** — agents can invoke RPCs, not install plugins.
3. **No advertisement refresh** — `_invalidate_caches()` alone does not update etcd registry or D2D presence payloads.
4. **No sub-device model** — `@on(device_id=…)` subscribes to *other* devices; it does not expose child devices under one JWT.
5. **No artifact channel** — no signed pull from portal; plugins are local directories.

### Credential model (important constraint)

Portal/NATS JWTs are scoped to **one** `device_id`. You cannot register multiple registry rows on a single credential. "Sub-devices" on one cred must be modeled as **additional RPC namespaces** on the host (e.g. `camera.snap`, `gps.read`) — which is exactly what capability loading does.

If you need separate fleet identities (distinct ACL, lifecycle, ownership), provision **additional devices** in portal or run separate `DeviceRuntime` processes (dcd pattern).

## Architecture

```
                    ┌─────────────────────────────────────┐
  Portal / Agents   │  plugin_host (one credential)       │
  invoke ──────────►│  ├─ host RPCs (load/unload/list)    │
                    │  ├─ in-process capabilities         │
                    │  └─ sidecar proxies (optional)      │
                    └──────────┬──────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
        capabilities/demo   capabilities/foo   Docker sidecar
        (in-process)        (in-process)       (HTTP → proxy)
```

### Mesh refresh after load

| Mode | Mechanism |
|------|-----------|
| Portal / infra | `DeviceRuntime._register(force=True)` |
| D2D / Zenoh | Update `PresenceAnnouncer._capabilities` + `trigger_burst()` |

the plugin driver performs this in `_refresh_mesh_advertisement()` after every load/unload/reload.

### Remote delivery (agent-installable)

Agents invoke delivery RPCs like any other function:

| RPC | Input |
|-----|-------|
| `install_plugin_from_url` | HTTPS URL + optional digest |
| `install_plugin_from_bundle` | base64 `.tar.gz` / `.zip` + optional digest |
| `install_plugin_from_docker` | `{type: docker, id, image, port, env, pull}` |
| `install_plugin_from_manifest` | Dispatches python (url/bundle) or docker manifests |

Python archives must contain `manifest.json` at root or in a single top-level folder.
Docker manifests deploy a **sidecar** proxied on the host credential (not a separate dcd device).

Security knobs: `DC_PLUGIN_INSTALL_URL_ALLOWLIST`, `DC_PLUGIN_INSTALL_REQUIRE_DIGEST`, `DC_PLUGIN_MAX_PLUGIN_BYTES`.

See `examples/plugin-manifests/README.md`.

### Agent authoring (discoverable on mesh)

Agents discover how to build plugins without reading the repo first:

1. **Device labels** on `plugin_host` — `plugin_driver:authoring_rpc`, `plugin_driver:template_rpc`
2. **`get_plugin_authoring_guide`** — workflow, manifest schema, install methods, doc URLs
3. **`get_plugin_template`** — rendered `manifest.json` + `capability.py` for a service id
4. **`list_plugin_examples`** — hello-world, demo, template paths
5. **`get_status.authoring`** — quick pointer block

Canonical template: `src/device_connect_plugin_driver/templates/plugin/`. Human playbook: [AGENTS.md](AGENTS.md).

Set `DC_PLUGIN_DOCS_BASE_URL` on the host so guide URLs point at your fork or docs site.

### Startup ordering

`DeviceRuntime` calls `driver.connect()` **before** `_register()`. the driver loads `auto_load` capabilities inside `connect()`, so the initial registry/presence snapshot includes bundled plugins.

Capability `@periodic` routines still start **after** registration (runtime calls `start_capability_routines()`), matching upstream behavior.

## Decision: Python harness vs concentrator

### Option A — In-process Python (default)

**Choose when:**

- Plugins are trusted or dev/test
- Dependencies are compatible
- Lowest latency and simplest ops

**Implementation:** `PluginHostDriver(CapabilityDriverMixin, DeviceDriver)`

### Option B — Sidecar concentrator (optional)

**Choose when:**

- Conflicting Python deps
- Privileged/isolated execution
- Still want **one** mesh identity

**Implementation:** `dc-plugin-sidecar` HTTP server + `SidecarConcentrator` (Docker) + `SidecarProxyRegistry` on the host.

Sidecars are **not** separate Device Connect devices; the host proxies their `/invoke/{fn}` endpoints.

### Option C — dcd / full containers (out of scope for plugin driver core)

**Choose when:**

- Each workload is a distinct fleet member
- You want compose-based deployment independent of the host process

Use [dcd](https://github.com/) (`docker_host` device). Each container typically runs its **own** driver + **own** `.creds.json`.

## Comparison to Waggle plugins

| | Waggle (`sage.yaml`) | plugin driver |
|---|---------------------|---------|
| Manifest | `sage.yaml` | `manifest.json` |
| Runtime | `waggle.plugin` + beekeeper | `device-connect-edge` |
| Discovery | Sage fabric | Device Connect registry / D2D |
| Packaging | Container image + Helm | Directory or sidecar image |

Bridging Waggle → Device Connect: run the Waggle container via dcd and optionally wrap publishes with a small DC driver, **or** rewrite the sensor logic as a Device Connect capability.

## Future work

Tracked in [TODO.md](TODO.md).

## File map

| Path | Role |
|------|------|
| `src/device_connect_plugin_driver/plugin_host.py` | Main driver |
| `src/device_connect_plugin_driver/sidecar.py` | Single-capability HTTP sidecar |
| `src/device_connect_plugin_driver/concentrator.py` | Docker deploy for sidecars |
| `src/device_connect_plugin_driver/sidecar_proxy.py` | Proxy sidecar RPCs on host |
| `capabilities/demo/` | Reference plugin (ping, echo) |
| `examples/hello-world/` | Minimal plugin for load/invoke testing |
