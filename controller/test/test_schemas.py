"""
Unit tests for controller.api.schemas module.
"""

import pytest
from pydantic import ValidationError

from controller.api.schemas import (
    ConfigSummary,
    HealthResponse,
    InfoResponse,
)


class TestHealthResponse:
    """Tests for HealthResponse model."""

    def test_valid_health_response(self):
        """Should create valid health response."""
        response = HealthResponse(
            status="healthy",
            version="1.0.0",
            docker_mode=False,
            drive_mounted=True,
        )
        assert response.status == "healthy"
        assert response.version == "1.0.0"
        assert response.docker_mode is False
        assert response.drive_mounted is True

    def test_health_response_serialization(self):
        """Should serialize to dict correctly."""
        response = HealthResponse(
            status="healthy",
            version="1.0.0",
            docker_mode=True,
            drive_mounted=False,
        )
        data = response.model_dump()
        assert data == {
            "status": "healthy",
            "version": "1.0.0",
            "docker_mode": True,
            "drive_mounted": False,
        }

    def test_health_response_missing_field(self):
        """Should raise validation error for missing required field."""
        with pytest.raises(ValidationError):
            HealthResponse(
                status="healthy",
                version="1.0.0",
                # missing docker_mode and drive_mounted
            )


class TestConfigSummary:
    """Tests for ConfigSummary model."""

    def test_valid_config_summary(self):
        """Should create valid config summary."""
        config = ConfigSummary(
            port=8087,
            media_directory="/media/wrolpi",
            managed_services_count=8,
        )
        assert config.port == 8087
        assert config.media_directory == "/media/wrolpi"
        assert config.managed_services_count == 8

    def test_config_summary_serialization(self):
        """Should serialize to dict correctly."""
        config = ConfigSummary(
            port=9999,
            media_directory="/custom/path",
            managed_services_count=5,
        )
        data = config.model_dump()
        assert data == {
            "port": 9999,
            "media_directory": "/custom/path",
            "managed_services_count": 5,
        }


class TestInfoResponse:
    """Tests for InfoResponse model."""

    def test_valid_info_response(self):
        """Should create valid info response with nested config."""
        response = InfoResponse(
            version="1.0.0",
            docker_mode=False,
            drive_mounted=True,
            config=ConfigSummary(
                port=8087,
                media_directory="/media/wrolpi",
                managed_services_count=8,
            ),
        )
        assert response.version == "1.0.0"
        assert response.docker_mode is False
        assert response.drive_mounted is True
        assert response.config.port == 8087

    def test_info_response_serialization(self):
        """Should serialize nested model correctly."""
        response = InfoResponse(
            version="1.0.0",
            docker_mode=True,
            drive_mounted=False,
            config=ConfigSummary(
                port=8087,
                media_directory="/media/wrolpi",
                managed_services_count=8,
            ),
        )
        data = response.model_dump()
        assert data["config"]["port"] == 8087
        assert data["config"]["media_directory"] == "/media/wrolpi"
