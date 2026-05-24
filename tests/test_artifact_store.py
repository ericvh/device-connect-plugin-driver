"""Tests for local plugin artifact store."""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp import ClientSession

from device_connect_plugin_driver.artifact_store import ArtifactServer, ArtifactStore, ArtifactStoreConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
HELLO_WORLD = REPO_ROOT / "examples" / "hello-world"


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    config = ArtifactStoreConfig(
        artifact_dir=tmp_path / "artifacts",
        serve_host="127.0.0.1",
        serve_port=8799,
        public_base_url=None,
    )
    return ArtifactStore(config)


def test_publish_and_list(store: ArtifactStore) -> None:
    record = store.publish_plugin_dir(HELLO_WORLD)
    assert record.plugin_id == "hello-world"
    artifacts = store.list_artifacts()
    assert len(artifacts) == 1
    assert artifacts[0]["plugin_id"] == "hello-world"
    assert artifacts[0]["url"].endswith(".tgz")


def test_get_artifact(store: ArtifactStore) -> None:
    store.publish_plugin_dir(HELLO_WORLD, version="0.1.0")
    artifact = store.get_artifact("hello-world", version="0.1.0")
    assert artifact is not None
    assert artifact["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_artifact_server_download(store: ArtifactStore) -> None:
    record = store.publish_plugin_dir(HELLO_WORLD)
    config = store._config  # noqa: SLF001
    server = ArtifactServer(store, host=config.serve_host, port=config.serve_port)
    await server.start()
    try:
        url = store.get_artifact(record.plugin_id)["url"]
        assert record.plugin_id in url

        async with ClientSession() as session:
            async with session.get(url) as resp:
                assert resp.status == 200
                body = await resp.read()
                assert len(body) == record.size
    finally:
        await server.stop()
