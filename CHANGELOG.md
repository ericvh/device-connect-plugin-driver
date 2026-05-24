# Changelog

All notable changes to **device-connect-plugin-driver** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-05-24

### Changed

- Docker CI builds and pushes **multi-arch** images (`linux/amd64`, `linux/arm64`) to GHCR

## [0.1.0] - 2026-05-24

### Added

- Initial **Device Connect plugin host driver** (`device_type = plugin_host`)
- Docker: production [Dockerfile](Dockerfile), [.dockerignore](.dockerignore), [compose.yaml](compose.yaml); GHCR workflow for host and sidecar images
- `dc-plugin-deploy` CLI — install/load/list/invoke plugins on a remote `plugin_host` over NATS
- Local plugin artifact store and delivery RPCs; `dc-plugin-driver validate` / `artifact` subcommands
- Opt-in manifest dependency install; `plugin_loaded` / `plugin_unloaded` events
- [SECURITY.md](SECURITY.md) threat model
- CI: loopback D2D test, two-process NATS integration, `examples/portal-provision.sh`, `docs/PUBLISHING.md`
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

[0.1.1]: https://github.com/ericvh/device-connect-plugin-driver/releases/tag/v0.1.1
[0.1.0]: https://github.com/ericvh/device-connect-plugin-driver/releases/tag/v0.1.0
