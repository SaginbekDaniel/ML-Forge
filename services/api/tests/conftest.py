"""API test fixtures.

A curriculum DB is seeded ONCE per session through the real pipeline (static
validation + sandbox validation when Docker is available) and copied per test.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mlforge_api.config import REPO_ROOT, Settings
from mlforge_runner import DockerSandbox

CONTENT = REPO_ROOT / "content" / "curriculum"


def docker_ok() -> bool:
    return DockerSandbox().health(max_age_s=0).available


@pytest.fixture(scope="session")
def seeded_template(tmp_path_factory) -> Path:
    from mlforge_api.cli import main as cli_main

    root = tmp_path_factory.mktemp("template")
    db = root / "mlforge.db"
    import os

    os.environ["MLFORGE_DATABASE_URL"] = f"sqlite:///{db}"
    os.environ["MLFORGE_DATA_DIR"] = str(root)
    from mlforge_api.config import get_settings

    get_settings.cache_clear()
    if docker_ok():
        assert cli_main(["seed"]) == 0
    else:  # content still loads; exercises stay inactive ("pending")
        assert cli_main(["seed"]) == 2
    get_settings.cache_clear()
    del os.environ["MLFORGE_DATABASE_URL"]
    del os.environ["MLFORGE_DATA_DIR"]
    return db


def make_settings(data_dir: Path) -> Settings:
    return Settings(
        data_dir=data_dir,
        database_url=f"sqlite:///{data_dir / 'mlforge.db'}",
        content_dir=CONTENT,
        anthropic_api_key=None,
        worker_threads=2,
    )


@pytest.fixture
def data_dir(tmp_path, seeded_template) -> Path:
    shutil.copy(seeded_template, tmp_path / "mlforge.db")
    return tmp_path


@pytest.fixture
def client(data_dir) -> Iterator[TestClient]:
    from mlforge_api.main import create_app

    app = create_app(make_settings(data_dir), start_worker=True)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def profile(client) -> dict:
    r = client.post("/api/v1/profile", json={"display_name": "Tester"})
    assert r.status_code == 201, r.text
    return r.json()


requires_docker = pytest.mark.skipif(not docker_ok(), reason="Docker sandbox unavailable")
