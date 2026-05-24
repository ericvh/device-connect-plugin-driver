# TODO — device-connect-plugin-driver

## Near term

- [ ] GitHub Actions CI (Python 3.12/3.13, ruff, pytest)
- [ ] Integration test: two-process D2D load_plugin → hello_world invoke
- [ ] Publish package to PyPI (`pip install device-connect-plugin-driver`)
- [ ] `examples/portal-provision.sh` — sample `dc-portalctl devices provision` for `plugin_host`

## Plugin platform

- [x] `install_plugin_from_url` with digest verification + URL allowlist
- [x] `install_plugin_from_bundle` (base64 archive)
- [x] `install_plugin_from_docker` / unified `install_plugin_from_manifest`
- [x] Agent authoring guide + template RPCs + AGENTS.md
- [ ] Portal artifact store (hosting); today URL must be HTTPS you control
- [ ] Opt-in dependency install (`pip install` from manifest with sandbox)
- [ ] Plugin validation CLI (`dc-plugin-driver validate capabilities/my-plugin`)
- [ ] Emit `plugin_loaded` / `plugin_unloaded` from host RPC handlers (decorators exist, not wired)

## Upstream device-connect

- [ ] Propose public `DeviceRuntime.refresh_advertisement()` (replace private `_register` / announcer poke)
- [ ] Contribute reference `plugin_host` pattern or docs to device-connect examples
- [ ] Capability load before first register — document contract in edge README

## Sidecar / concentrator

- [ ] Health-check sidecars before registering proxied RPCs
- [ ] Sidecar function schemas merged into host capability advertisement
- [ ] Rootless / podman support
- [ ] CI job building `Dockerfile.sidecar` and running hello-world in sidecar mode

## Adapters

- [ ] Waggle adapter: wrap `sage.yaml` plugins via subprocess or dcd sidecar
- [ ] OpenAPI capability generator (thin wrapper like openapi-device-connect)

## Quality

- [x] Unit tests for plugin host load/unload and mesh refresh hooks
- [x] hello-world example + `tests/test_hello_world.py`
- [ ] Contract test against pinned `device-connect-edge` version matrix
- [ ] Document recommended NATS subject limits when many plugins expose many RPCs
