# Changelog

All notable changes to **device-connect-plugin-driver** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- CI: loopback D2D test in unit job; two-process NATS integration job
- Near-term TODO items completed (integration tests, portal-provision.sh, PyPI publish workflow)

### Added

- Docker: production [Dockerfile](Dockerfile), [.dockerignore](.dockerignore), [compose.yaml](compose.yaml) with volumes for capabilities/artifacts/creds
- GitHub Actions [.github/workflows/docker.yml](.github/workflows/docker.yml) — build and push `device-connect-plugin-driver` and `dc-plugin-sidecar` to GHCR
- `dc-plugin-deploy` CLI — install/load/list/invoke plugins on a remote `plugin_host` over NATS
- Local plugin artifact store (`ArtifactStore`, `publish_plugin_artifact`, `list_plugin_artifacts`, `get_plugin_artifact_url` RPCs)
- `dc-plugin-driver artifact publish|list|serve` and `dc-plugin-driver validate` CLI subcommands
- Opt-in manifest dependency install (`DC_PLUGIN_INSTALL_DEPENDENCIES=1`, per-RPC `install_dependencies`)
- `plugin_loaded` / `plugin_unloaded` events emitted on load/unload/reload and sidecar deploy
- `tests/test_plugin_validation.py`, `tests/test_artifact_store.py`, `tests/test_plugin_host_events.py`
- `tests/test_d2d_loopback.py` — loopback messaging D2D load/invoke test
- `tests/integration/` — two-process NATS integration test + plugin host runner
- `examples/portal-provision.sh` — dc-portalctl sample for plugin_host
- `.github/workflows/publish.yml` — PyPI publish on GitHub release
- `docs/PUBLISHING.md` — PyPI trusted publishing instructions
- PyPI classifiers and project URLs in `pyproject.toml`
- Renamed from decente working name; package `device_connect_plugin_driver`, env prefix `DC_PLUGIN_*`

## [0.1.0] - 2026-05-24

### Added

- Initial **Device Connect plugin host driver** (`device_type = plugin_host`)
- In-process capability loading via `CapabilityDriverMixin`
- Host RPCs: `get_status`, `list_plugins`, `load_plugin`, `unload_plugin`, `reload_plugin`, `install_plugin`
- Mesh advertisement refresh after load/unload (portal re-register + D2D presence burst)
- Optional Docker sidecar concentrator: `deploy_sidecar`, `undeploy_sidecar`, `dc-plugin-sidecar` CLI
- Bundled `capabilities/demo/` reference plugin (`ping`, `echo`)
- `examples/hello-world/` smoke-test plugin
- Portal and D2D runtime configuration (mirrors dcd launcher pattern)
- Documentation: README, DESIGN, TODO, CHANGELOG
- Dockerfile, `Dockerfile.sidecar`, `compose.yaml`
- Unit tests: `test_plugin_host`, `test_config`, `test_hello_world`
- Apache-2.0 license

[0.1.0]: https://github.com/ericvh/device-connect-plugin-driver/releases/tag/v0.1.0
