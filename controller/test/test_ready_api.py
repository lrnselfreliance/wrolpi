"""
Tests for the /api/ready readiness endpoint.
"""

from unittest import mock


class TestReadyEndpoint:
    """Tests for /api/ready endpoint."""

    def test_ready_both_down(self, test_client):
        with mock.patch("controller.api.ready.check_api_ready", return_value=False):
            with mock.patch("controller.api.ready.check_app_ready", return_value=False):
                response = test_client.get("/api/ready")
                assert response.status_code == 200
                data = response.json()
                assert data["api"] is False
                assert data["app"] is False

    def test_ready_both_up(self, test_client):
        with mock.patch("controller.api.ready.check_api_ready", return_value=True):
            with mock.patch("controller.api.ready.check_app_ready", return_value=True):
                response = test_client.get("/api/ready")
                assert response.status_code == 200
                data = response.json()
                assert data["api"] is True
                assert data["app"] is True

    def test_ready_api_up_app_down(self, test_client):
        with mock.patch("controller.api.ready.check_api_ready", return_value=True):
            with mock.patch("controller.api.ready.check_app_ready", return_value=False):
                response = test_client.get("/api/ready")
                data = response.json()
                assert data["api"] is True
                assert data["app"] is False

    def test_ready_api_down_app_up(self, test_client):
        with mock.patch("controller.api.ready.check_api_ready", return_value=False):
            with mock.patch("controller.api.ready.check_app_ready", return_value=True):
                response = test_client.get("/api/ready")
                data = response.json()
                assert data["api"] is False
                assert data["app"] is True
