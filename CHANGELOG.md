# Changelog

All notable changes to **device-connect-plugin-driver** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Renamed project from **decente** to **device-connect-plugin-driver** (package `device_connect_plugin_driver`, CLI `device-connect-plugin-driver`)
- Environment prefix `DECENTE_*` → `DC_PLUGIN_*`; mesh labels `decente:*` → `plugin_driver:*`

### Added

- `AGENTS.md` — agent playbook for authoring, packaging, and installing plugins
- `get_plugin_authoring_guide`, `get_plugin_template`, `list_plugin_examples` RPCs
- `src/device_connect_plugin_driver/authoring.py` + packaged `src/device_connect_plugin_driver/templates/plugin/`
- `examples/plugin-template/` — pre-rendered my-service example
- Device labels for mesh discoverability (`plugin_driver:authoring_rpc`, etc.)
- `tests/test_authoring.py`
- `install_plugin_from_url` — HTTPS download + digest-verified extract
- `install_plugin_from_bundle` — base64 archive install
- `install_plugin_from_docker` — docker manifest sidecar deploy (proxied on host)
- `install_plugin_from_manifest` — unified python/docker manifest dispatcher
- `src/device_connect_plugin_driver/plugin_delivery.py` — fetch, verify, extract helpers
- `examples/plugin-manifests/` — docker manifest sample + delivery docs
- `tests/test_plugin_delivery.py`

### Changed

- `SidecarSpec` supports image-only deploy (optional capability mount)
- README and DESIGN document remote agent delivery flow

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

[0.1.0]: https://github.com/example/device-connect-plugin-driver/releases/tag/v0.1.0
