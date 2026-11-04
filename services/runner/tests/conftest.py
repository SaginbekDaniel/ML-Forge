import pytest
from mlforge_runner import DockerSandbox


@pytest.fixture(scope="session")
def sandbox() -> DockerSandbox:
    sb = DockerSandbox()
    health = sb.health(max_age_s=0)
    if not health.available:
        pytest.skip(f"Docker sandbox unavailable: {health.reason} (run `make runner-build`)")
    return sb
