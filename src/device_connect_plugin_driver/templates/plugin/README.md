# Plugin template

Copy this folder to create a new Device Connect capability, or call `get_plugin_template` on a
`plugin_host` device to receive rendered files.

## Required files

| File | Purpose |
|------|---------|
| `manifest.json` | Plugin id, class name, entry point, optional Python deps |
| `capability.py` | Class with `@rpc` / `@emit` / `@periodic` methods |

## Placeholders (when using `get_plugin_template`)

- `{{PLUGIN_ID}}` — directory name / manifest id (e.g. `garage-door`)
- `{{CLASS_NAME}}` — Python class (e.g. `GarageDoorCapability`)
- `{{DESCRIPTION}}` — human-readable summary

## Install on a host

```bash
tar -czf my-plugin.tgz -C capabilities my-plugin
# then install_plugin_from_url / install_plugin_from_bundle / install_plugin
```

See [AGENTS.md](../../../AGENTS.md) for the full agent playbook.
