"""
Unit tests for controller.api.schemas module.
"""

import pytest
from pydantic import ValidationError

from controller.api.schemas import HealthResponse


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
