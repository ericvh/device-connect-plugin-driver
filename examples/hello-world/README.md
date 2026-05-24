# hello-world example

Minimal plugin for testing **plugin addition** and **RPC access** on a the `plugin_host` driver.

## Layout

```
examples/hello-world/
  manifest.json
  capability.py   # exposes hello_world(name="world")
```

## Local smoke test (no mesh)

From the repo root with the venv active:

```bash
cd ~/src/device-connect-plugin-driver
source .venv/bin/activate
pytest tests/test_hello_world.py -q
```

## D2D end-to-end

**Terminal 1 — start host without auto-loading plugins:**

```bash
export DEVICE_CONNECT_ALLOW_INSECURE=true
device-connect-plugin-driver \
  --allow-insecure \
  --no-auto-load \
  --device-id plugin-host-1 \
  --tenant dev \
  --capabilities-dir ./capabilities
```

**Terminal 2 — install and invoke** (using a second driver process or agent-tools):

If you copied the example into `capabilities/` first:

```bash
cp -R examples/hello-world capabilities/
```

Then invoke on the host (via your usual Device Connect client):

```text
load_plugin   {"plugin_id": "hello-world"}
hello_world   {"name": "plugin"}
```

Expected result:

```json
{"message": "Hello, plugin!"}
```

Or install directly from the example path without copying:

```text
install_plugin {"source_path": "/Users/erivan01/src/device_connect_plugin_driver/examples/hello-world"}
hello_world    {}
```

## Portal end-to-end

1. Provision one `plugin_host` device in the portal.
2. Start the plugin driver with `--portal` and that device's `.creds.json`.
3. From an agent or `dc-portalctl`:

```bash
dc-portalctl devices invoke plugin-host-1 install_plugin \
  --params '{"source_path": "/path/to/device-connect-plugin-driver/examples/hello-world"}'

dc-portalctl devices invoke plugin-host-1 hello_world \
  --params '{"name": "portal"}'
```

4. Confirm `hello_world` appears in `dc-portalctl devices capabilities plugin-host-1` after load.

## Unload

```text
unload_plugin {"plugin_id": "hello-world"}
```

After unload, `hello_world` should no longer appear in the host capability list.
