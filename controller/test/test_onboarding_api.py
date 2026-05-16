"""
Integration tests for onboarding API endpoints.
"""

from unittest import mock

import pytest


class TestOnboardingDockerAndMounted:
    """Cross-cutting behaviour: Docker mode → 501; drive already mounted → 409."""

    @pytest.mark.parametrize("method,endpoint,payload", [
        ("get", "/api/onboarding/candidates", None),
        ("post", "/api/onboarding/probe", {"device_path": "/dev/sda1", "fstype": "ext4"}),
        ("post", "/api/onboarding/commit", {"device_path": "/dev/sda1", "fstype": "ext4"}),
        ("post", "/api/onboarding/cancel", None),
    ])
    def test_endpoint_returns_501_in_docker(self, test_client_docker_mode, method, endpoint, payload):
        client_call = getattr(test_client_docker_mode, method)
        response = client_call(endpoint, json=payload) if payload else client_call(endpoint)
        assert response.status_code == 501

    @pytest.mark.parametrize("method,endpoint,payload", [
        ("get", "/api/onboarding/candidates", None),
        ("post", "/api/onboarding/probe", {"device_path": "/dev/sda1", "fstype": "ext4"}),
    ])
    def test_endpoint_returns_409_when_drive_mounted(self, test_client, method, endpoint, payload):
        """Onboarding endpoints reject when the primary drive is already mounted."""
        with mock.patch("controller.api.onboarding.is_primary_drive_mounted", return_value=True):
            client_call = getattr(test_client, method)
            response = client_call(endpoint, json=payload) if payload else client_call(endpoint)
            assert response.status_code == 409


class TestOnboardingCandidatesEndpoint:
    """Tests for GET /api/onboarding/candidates."""

    def test_returns_candidates(self, test_client):
        """Should return list of unmounted drives."""
        with mock.patch(
            "controller.api.onboarding.is_primary_drive_mounted", return_value=False,
        ), mock.patch(
            "controller.api.onboarding.get_onboarding_candidates",
            return_value=[{
                "path": "/dev/sda1", "name": "sda1", "size": "500G",
                "fstype": "ext4", "label": None, "uuid": "abc-123", "model": "SanDisk",
            }],
        ):
            response = test_client.get("/api/onboarding/candidates")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["path"] == "/dev/sda1"

    def test_returns_empty_list(self, test_client):
        """Should return empty list when no unmounted drives."""
        with mock.patch(
            "controller.api.onboarding.is_primary_drive_mounted", return_value=False,
        ), mock.patch(
            "controller.api.onboarding.get_onboarding_candidates", return_value=[],
        ):
            response = test_client.get("/api/onboarding/candidates")
            assert response.status_code == 200
            assert response.json() == []


class TestOnboardingProbeEndpoint:
    """Tests for POST /api/onboarding/probe."""

    def test_probe_success_with_config(self, test_client):
        """Should return probe result with config found."""
        with mock.patch(
            "controller.api.onboarding.is_primary_drive_mounted", return_value=False,
        ), mock.patch(
            "controller.api.onboarding.probe_drive",
            return_value={
                "success": True,
                "config_found": True,
                "mounts": [{"device": "/dev/sda1", "mount_point": "/media/wrolpi"}],
                "device_path": "/dev/sda1",
                "fstype": "ext4",
            },
        ):
            response = test_client.post(
                "/api/onboarding/probe",
                json={"device_path": "/dev/sda1", "fstype": "ext4"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["config_found"] is True
            assert len(data["mounts"]) == 1

    def test_probe_failure(self, test_client):
        """Should return 500 when probe fails."""
        with mock.patch(
            "controller.api.onboarding.is_primary_drive_mounted", return_value=False,
        ), mock.patch(
            "controller.api.onboarding.probe_drive",
            return_value={"success": False, "error": "Mount failed"},
        ):
            response = test_client.post(
                "/api/onboarding/probe",
                json={"device_path": "/dev/sda1", "fstype": "ext4"},
            )
            assert response.status_code == 500


class TestOnboardingCommitEndpoint:
    """Tests for POST /api/onboarding/commit."""

    def test_commit_success(self, test_client):
        """Should return success on commit."""
        with mock.patch(
            "controller.api.onboarding.commit_onboarding",
            return_value={
                "success": True,
                "mounts": ["/media/wrolpi"],
                "repair_started": True,
            },
        ):
            response = test_client.post(
                "/api/onboarding/commit",
                json={"device_path": "/dev/sda1", "fstype": "ext4"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["repair_started"] is True

    def test_commit_failure(self, test_client):
        """Should return 500 on failure."""
        with mock.patch(
            "controller.api.onboarding.commit_onboarding",
            return_value={"success": False, "error": "Device busy"},
        ):
            response = test_client.post(
                "/api/onboarding/commit",
                json={"device_path": "/dev/sda1", "fstype": "ext4"},
            )
            assert response.status_code == 500

    def test_commit_shadowed_data_returns_structured_block(self, test_client):
        """Shadowed-data soft-block returns 200 with needs_force=shadowed."""
        with mock.patch(
            "controller.api.onboarding.commit_onboarding",
            return_value={
                "success": False,
                "needs_force": "shadowed",
                "shadowed_data": {"size_bytes": 1024, "entries": ["videos"]},
                "error": "Existing data",
                "mounts": [],
                "repair_started": False,
            },
        ):
            response = test_client.post(
                "/api/onboarding/commit",
                json={"device_path": "/dev/sda1", "fstype": "ext4"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert data["needs_force"] == "shadowed"
            assert data["shadowed_data"] == {"size_bytes": 1024, "entries": ["videos"]}

    def test_commit_forwards_force_shadowed(self, test_client):
        """force_shadowed is forwarded to commit_onboarding."""
        with mock.patch(
            "controller.api.onboarding.commit_onboarding",
            return_value={"success": True, "mounts": [], "repair_started": False},
        ) as mock_commit:
            response = test_client.post(
                "/api/onboarding/commit",
                json={
                    "device_path": "/dev/sda1",
                    "fstype": "ext4",
                    "force_shadowed": True,
                },
            )
            assert response.status_code == 200
            mock_commit.assert_called_once_with(
                device_path="/dev/sda1",
                fstype="ext4",
                force_shadowed=True,
            )


class TestOnboardingCancelEndpoint:
    """Tests for POST /api/onboarding/cancel."""

    def test_cancel_success(self, test_client):
        """Should return success on cancel."""
        with mock.patch(
            "controller.api.onboarding.cancel_probe",
            return_value={"success": True},
        ):
            response = test_client.post("/api/onboarding/cancel")
            assert response.status_code == 200
