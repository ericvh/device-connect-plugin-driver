# plugin-template example

Pre-rendered copy of `src/device_connect_plugin_driver/templates/plugin/` with id **`my-service`**.

## Use as a starting point

```bash
cp -R examples/plugin-template capabilities/my-service
# edit manifest.json + capability.py
```

Or generate fresh files for your service id via the mesh:

```text
get_plugin_template {
  "plugin_id": "garage-door",
  "description": "Controls the garage door opener"
}
```

## Test install (local path)

```text
install_plugin {"source_path": "/path/to/device-connect-plugin-driver/examples/plugin-template", "plugin_id": "my-service"}
get_service_status {}
```

See [AGENTS.md](../../AGENTS.md) for the full agent playbook.
