"""
Pytest fixtures for Controller tests.
"""
import copy
import tempfile
from pathlib import Path
from typing import Generator
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from controller.defaults import DEFAULT_CONFIG


@pytest.fixture
def test_directory() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir).resolve()
        tmp_path.chmod(0o40755)
        yield tmp_path


@pytest.fixture
def test_config_directory(test_directory: Path) -> Path:
    """Create a config directory inside test_directory."""
    config_dir = test_directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


@pytest.fixture
def mock_config_path(test_config_directory: Path):
    """Mock the CONFIG_PATH_ON_DRIVE to use test directory."""
    config_path = test_config_directory / "controller.yaml"
    with mock.patch("controller.lib.config.CONFIG_PATH_ON_DRIVE", config_path):
        yield config_path


@pytest.fixture
def reset_runtime_config():
    """Reset the runtime config to defaults before and after each test."""
    import controller.lib.config as config_module

    # Save original
    original = copy.deepcopy(config_module._runtime_config)

    # Reset to defaults
    config_module._runtime_config = copy.deepcopy(DEFAULT_CONFIG)

    yield

    # Restore original
    config_module._runtime_config = original


@pytest.fixture
def mock_docker_mode():
    """Mock Docker mode to be disabled."""
    with mock.patch.dict("os.environ", {"DOCKERIZED": "false"}):
        yield


@pytest.fixture
def mock_docker_mode_enabled():
    """Mock Docker mode to be enabled."""
    with mock.patch.dict("os.environ", {"DOCKERIZED": "true"}):
        yield


@pytest.fixture
def mock_drive_mounted(test_config_directory: Path):
    """Mock the primary drive as mounted by creating config directory."""
    # test_config_directory fixture already creates it
    with mock.patch(
            "controller.lib.config.is_primary_drive_mounted", return_value=True
    ):
        yield test_config_directory


@pytest.fixture
def mock_drive_not_mounted():
    """Mock the primary drive as not mounted."""
    with mock.patch(
            "controller.lib.config.is_primary_drive_mounted", return_value=False
    ):
        yield


@pytest.fixture
def test_client(reset_runtime_config, mock_docker_mode) -> TestClient:
    """Create a FastAPI TestClient for integration testing."""
    from controller.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def test_client_docker_mode(reset_runtime_config, mock_docker_mode_enabled) -> TestClient:
    """Create a FastAPI TestClient with Docker mode enabled."""
    from controller.main import app

    with TestClient(app) as client:
        yield client
