# Security — device-connect-plugin-driver threat model

This document describes security-relevant behavior of the **plugin host** driver (`device_type = plugin_host`). It is intended for operators, integrators, and agents that install or invoke plugins over Device Connect.

See also: [README.md](README.md) · [DESIGN.md](DESIGN.md) · [AGENTS.md](AGENTS.md)

---

## Scope

**In scope**

- `PluginHostDriver` and its host management RPCs (`load_plugin`, `install_plugin_from_*`, etc.)
- In-process Python capability loading (`CapabilityDriverMixin`)
- Optional Docker sidecar concentrator and HTTP proxying
- Local artifact store and CLI delivery helpers
- Opt-in manifest dependency installation

**Out of scope**

- Device Connect portal authentication, NATS ACL design, and tenant policy (upstream `device-connect` / `device-connect-server`)
- Security of third-party plugins you choose to install
- Host OS hardening, network firewalls, and physical access controls

---

## Assets

| Asset | Why it matters |
|-------|----------------|
| **Host process** | Runs with the OS identity of the plugin host; can access local filesystem, env, and network allowed to that user |
| **Portal / mesh credential** | One JWT typically maps to one `device_id`; compromise grants invoke access to every host RPC and loaded plugin RPC |
| **`capabilities_dir`** | Writable plugin tree; malicious archives or copies can persist code on disk |
| **Sidecar containers** | Isolated processes still share the host kernel; misconfiguration can expose mounts or host ports |
| **Dependency sandboxes** (`.deps/`) | Per-plugin pip `--target` trees; supply-chain packages run at install time |
| **Artifact store** (`.artifacts/`) | Published plugin archives; if served over HTTP, readable by anyone who can reach the listener |
| **Secrets in host env** | Upstream API keys, serial devices, etc. are visible to in-process plugins via `device` / host imports |

---

## Actors and trust boundaries

```
  ┌─────────────┐     invoke (ACL)      ┌──────────────────┐
  │ Portal /    │ ───────────────────►  │ plugin_host      │
  │ agents /    │                       │ (one credential) │
  │ peer devices│ ◄── events / RPC ──── │                  │
  └─────────────┘                       └────────┬─────────┘
                                                 │
                    untrusted after install      │
                                                 ▼
                                    ┌────────────────────────┐
                                    │ Plugins (in-process)   │
                                    │ Sidecars (containers)  │
                                    │ pip sandboxes (.deps)  │
                                    └────────────────────────┘
```

| Actor | Trust level | Typical capability |
|-------|-------------|------------------|
| **Host owner / operator** | Fully trusted | Starts driver, sets env, owns disk and Docker socket |
| **Portal tenant admin** | Trusted for provisioning | Issues device credentials, configures NATS ACL |
| **Mesh caller with `devices:invoke`** | **Trusted for RCE** | Can call `install_plugin_from_*`, `load_plugin`, `publish_plugin_artifact` |
| **Plugin author** | **Untrusted** | Code runs after install; treat like any third-party package |
| **Artifact / URL origin** | **Untrusted until verified** | CDN, GitHub releases, local artifact HTTP server |
| **Docker registry** | **Untrusted until pinned** | Images pulled for sidecar deploy |

**Critical assumption:** anyone who can invoke install/load RPCs on the host is equivalent to **remote code execution** on that machine. Device Connect ACLs are the primary gate — not sandboxing inside the driver.

---

## Threat catalog

### T1 — Malicious plugin install (RCE)

**Description.** Caller invokes `install_plugin_from_bundle`, `install_plugin_from_url`, `install_plugin`, or `load_plugin` with attacker-controlled code.

**Impact.** Arbitrary Python in the host process; access to host filesystem (within OS permissions), network, and secrets available to the process.

**Built-in mitigations.**

- None that prevent execution after a successful install — by design, plugins are code.
- Archive extraction uses path traversal checks (`_safe_extract_tar` / `_safe_extract_zip`).
- `DC_PLUGIN_MAX_PLUGIN_BYTES` caps download/bundle size (default 10 MiB).

**Recommendations.**

- Restrict invoke ACL so only trusted principals can call install/load RPCs.
- Prefer **digest pinning** (`sha256:…`) and set `DC_PLUGIN_INSTALL_REQUIRE_DIGEST=1`.
- Validate plugins offline: `dc-plugin-driver validate path/to/plugin`.
- Run the host under a dedicated OS user with minimal filesystem access.

---

### T2 — Supply-chain via URL install

**Description.** Attacker compromises an HTTPS artifact URL, DNS, or CDN; host downloads trojaned archive.

**Impact.** Same as T1.

**Built-in mitigations.**

- Optional `digest` verification on URL and bundle installs.
- `DC_PLUGIN_INSTALL_URL_ALLOWLIST` restricts URL hostnames (exact or subdomain suffix match).
- HTTPS only via `aiohttp` fetch (no automatic downgrade).

**Gaps.**

- Allowlist empty → any HTTPS host is permitted.
- Digest optional unless `DC_PLUGIN_INSTALL_REQUIRE_DIGEST=1`.
- TLS certificate validation follows aiohttp defaults; no certificate pinning.

**Recommendations.**

- Always set allowlist and require digest in production.
- Host artifacts on infrastructure you control or sign releases out-of-band.

---

### T3 — Base64 bundle abuse

**Description.** Large or malformed bundles sent to `install_plugin_from_bundle`.

**Impact.** DoS (memory), failed installs, or extractor errors.

**Built-in mitigations.**

- Base64 decode validation and max byte limit (`DC_PLUGIN_MAX_PLUGIN_BYTES`).
- Safe archive extraction with rejection of path traversal members.

**Recommendations.**

- Keep max bytes low for your deployment size; monitor host memory.

---

### T4 — Local artifact store exposure

**Description.** Operator enables `DC_PLUGIN_ARTIFACT_SERVE=1` or `dc-plugin-driver artifact serve`. HTTP listener defaults to `127.0.0.1:8790` but can be misconfigured.

**Impact.** Unauthenticated read of published plugin archives; combined with weak install ACL, enables chain install from `install_plugin_from_url`.

**Built-in mitigations.**

- Default bind address is loopback (`DC_PLUGIN_ARTIFACT_HOST=127.0.0.1`).
- Artifact dir lives under `capabilities_dir/.artifacts` (hidden from `list_plugins`).

**Gaps.**

- No authentication on artifact HTTP server.
- `publish_plugin_artifact` RPC can be invoked by any caller with host invoke access.

**Recommendations.**

- Do not expose artifact HTTP to untrusted networks.
- Put a reverse proxy with auth/TLS in front if remote fetch is required (`DC_PLUGIN_ARTIFACT_PUBLIC_URL`).
- Treat `publish_plugin_artifact` like an install RPC for ACL purposes.

---

### T5 — Opt-in pip dependency install

**Description.** With `DC_PLUGIN_INSTALL_DEPENDENCIES=1` or `install_dependencies=true`, host runs `pip install --target .deps/{plugin_id}/…` for manifest-declared packages.

**Impact.**

- **Install-time RCE:** malicious or typosquatted PyPI packages execute setup code during pip.
- **Dependency confusion** if package names are attacker-influenced.
- Installed wheels importable by that plugin via injected `sys.path`.

**Built-in mitigations.**

- **Off by default**; must opt in globally or per RPC.
- Per-plugin isolated `--target` directory (not global site-packages).
- Timeout via `DC_PLUGIN_INSTALL_DEPENDENCIES_TIMEOUT` (default 120s).

**Gaps.**

- No PyPI index allowlist, hash pinning, or offline wheel cache.
- pip runs as the same OS user as the host.

**Recommendations.**

- Pre-bake dependencies into host image or sidecar image instead of runtime pip.
- If runtime install is required, use an internal index and `--require-hashes` workflow (not yet supported by this driver).

---

### T6 — Docker sidecar deploy

**Description.** Caller invokes `install_plugin_from_docker`, `deploy_sidecar`, or docker-typed `install_plugin_from_manifest`.

**Impact.**

- Pull/run arbitrary container images if ACL allows.
- Capability directory bind-mounted read-only into container (`/capabilities/{plugin_id}`).
- Published host port mapped to sidecar HTTP API on localhost.

**Built-in mitigations.**

- Sidecars disabled unless `--enable-sidecars` / `DC_PLUGIN_ENABLE_SIDECARS=1`.
- Sidecar HTTP bound inside container; host proxy uses `127.0.0.1` mapped port.
- Optional image digest field on docker manifest (operator must enforce usage).

**Gaps.**

- No image signature verification or registry allowlist in driver.
- Docker socket access is all-or-nothing for the host user.
- Custom sidecar images may expose broader attack surface than `dc-plugin-sidecar`.

**Recommendations.**

- Restrict sidecar RPCs to admin callers.
- Pin images by digest; disable `pull: true` for production when using local trusted images.
- Run Docker with rootless/podman where possible (see [TODO.md](TODO.md)).

---

### T7 — Credential and secret leakage

**Description.** Plugin code reads portal tokens, NATS creds, or env secrets from the host process.

**Impact.** Lateral movement to other devices or portal APIs.

**Built-in mitigations.**

- Documentation warns not to embed JWTs in plugin bundles ([AGENTS.md](AGENTS.md)).

**Gaps.**

- In-process plugins share the host Python interpreter and can inspect process env and memory.
- Sidecars do not receive portal credentials by default but share the host network namespace policies of Docker.

**Recommendations.**

- Use sidecar mode for untrusted plugins.
- Inject secrets via host env only to trusted plugins; use separate portal devices for high-sensitivity workloads ([DESIGN.md](DESIGN.md)).

---

### T8 — Mesh advertisement and discovery spoofing

**Description.** Attacker registers a fake `plugin_host` or MITM D2D discovery.

**Impact.** Agents install plugins or invoke RPCs on the wrong device.

**Built-in mitigations.**

- Portal mode: registry and JWT scoped to provisioned `device_id`.
- D2D: depends on Device Connect Zenoh security settings (`DEVICE_CONNECT_ALLOW_INSECURE` is dev-only).

**Recommendations.**

- Never use `--allow-insecure` / `DEVICE_CONNECT_ALLOW_INSECURE=true` outside lab networks.
- Verify device identity and labels (`plugin_driver:role=plugin_host`) before install RPCs.

---

### T9 — Denial of service

**Description.** Repeated load/unload, large listings, or many plugins exhaust CPU, file descriptors, or registry churn.

**Impact.** Host or portal instability; mesh refresh storms from `_refresh_mesh_advertisement`.

**Built-in mitigations.**

- Bundle/URL size limits.
- pip install timeout.

**Gaps.**

- No rate limiting on install/load RPCs.
- No max loaded plugin count.

**Recommendations.**

- Rate-limit at portal/gateway; monitor `list_plugins` and registry update frequency.

---

### T10 — Privilege escalation via host management RPCs

**Description.** Caller chains RPCs: install plugin → plugin invokes `invoke_remote` on other devices, or uses host `device` reference.

**Impact.** Plugin becomes a pivot inside the mesh.

**Built-in mitigations.**

- Device Connect ACL on each target device still applies to `invoke_remote`.

**Recommendations.**

- Scope JWT invoke permissions narrowly.
- Audit loaded plugins and emitted `plugin_loaded` events.

---

## Security controls reference

| Control | Environment / RPC | Default |
|---------|-------------------|---------|
| URL host allowlist | `DC_PLUGIN_INSTALL_URL_ALLOWLIST` | Off (allow all HTTPS hosts) |
| Require digest | `DC_PLUGIN_INSTALL_REQUIRE_DIGEST=1` | Off |
| Max artifact size | `DC_PLUGIN_MAX_PLUGIN_BYTES` | 10 MiB |
| Runtime pip install | `DC_PLUGIN_INSTALL_DEPENDENCIES=1` | Off |
| Sidecars | `DC_PLUGIN_ENABLE_SIDECARS=1` | Off |
| Artifact HTTP serve | `DC_PLUGIN_ARTIFACT_SERVE=1` | Off |
| Artifact bind | `DC_PLUGIN_ARTIFACT_HOST` | `127.0.0.1` |
| Insecure D2D | `DEVICE_CONNECT_ALLOW_INSECURE` | Off (upstream) |

Host RPCs with **elevated sensitivity** (treat as admin):

- `install_plugin_from_url`, `install_plugin_from_bundle`, `install_plugin_from_manifest`, `install_plugin_from_docker`
- `install_plugin`, `load_plugin`, `reload_plugin`
- `publish_plugin_artifact`
- `deploy_sidecar`, `undeploy_sidecar`

---

## Recommended production baseline

1. Portal device with **minimal invoke ACL** — separate admin vs operator credentials if possible.
2. `DC_PLUGIN_INSTALL_REQUIRE_DIGEST=1` and `DC_PLUGIN_INSTALL_URL_ALLOWLIST` set to your artifact hosts.
3. **Do not** enable `DC_PLUGIN_INSTALL_DEPENDENCIES` on edge hosts; bake deps into image or use sidecars.
4. Sidecars **off** unless needed; if on, pin images by digest and restrict deploy RPCs.
5. Artifact server **loopback only** or behind authenticated TLS proxy.
6. Run host as **non-root** dedicated user; read-only rootfs where feasible.
7. `dc-plugin-driver validate` in CI before publishing artifacts.

---

## Vulnerability reporting

If you believe you have found a security issue in **device-connect-plugin-driver**, please report it responsibly:

1. **Do not** open a public GitHub issue for exploitable vulnerabilities.
2. Contact the repository maintainer via GitHub private security advisory or the contact listed on the repository homepage.
3. Include reproduction steps, impact assessment, and affected version.

For vulnerabilities in **device-connect** core (portal, NATS, edge runtime), follow the reporting process for [arm/device-connect](https://github.com/arm/device-connect).

---

## Document history

| Version | Date | Notes |
|---------|------|-------|
| 1.0 | 2026-05-24 | Initial threat model covering plugin platform delivery, sidecars, artifact store, dependency install |
