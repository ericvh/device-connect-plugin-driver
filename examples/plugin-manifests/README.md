# Plugin delivery manifests

Agents can install plugins on a `plugin_host` without SSH by invoking delivery RPCs.

## Python plugin — URL

Host a `.tar.gz` or `.zip` of a capability folder (must contain `manifest.json`):

```bash
# Package hello-world
tar -czf hello-world.tgz -C examples hello-world

# Invoke on the host (after uploading tgz to HTTPS)
install_plugin_from_url {
  "url": "https://artifacts.example.com/hello-world.tgz",
  "digest": "sha256:…",
  "format": "auto"
}
```

## Python plugin — base64 bundle

For small plugins, embed the archive directly:

```bash
B64=$(base64 < hello-world.tgz)
install_plugin_from_bundle {
  "bundle_b64": "<base64>",
  "digest": "sha256:…"
}
```

## Docker plugin — sidecar manifest

Deploy a container that exposes the dc-plugin sidecar HTTP API. RPCs are proxied through the host credential.

```json
{
  "type": "docker",
  "id": "hello-sidecar",
  "image": "dc-plugin-sidecar:local",
  "port": 8787,
  "pull": false,
  "env": {
    "DC_PLUGIN_CAPABILITY_DIR": "/capabilities/hello-world",
    "DC_PLUGIN_PLUGIN_ID": "hello-world"
  }
}
```

Invoke:

```text
install_plugin_from_docker {"manifest": { … }}
```

Or pass the same object to `install_plugin_from_manifest` with `"type": "docker"`.

### dcd-style full containers

If the plugin must be a **separate Device Connect device** (own credential), use **dcd** on the same host instead of plugin driver docker manifest mode. plugin driver docker manifests always proxy through the `plugin_host` identity.

## Digest pinning

Optional but recommended. Compute with:

```bash
shasum -a 256 hello-world.tgz | awk '{print "sha256:" $1}'
```

Set `DC_PLUGIN_INSTALL_REQUIRE_DIGEST=1` on the host to reject installs without a matching digest.

## URL allowlist

Set on the host:

```bash
export DC_PLUGIN_INSTALL_URL_ALLOWLIST=artifacts.example.com,github.com
```
