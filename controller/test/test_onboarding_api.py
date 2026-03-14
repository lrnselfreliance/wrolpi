"""
Integration tests for onboarding API endpoints.
"""

from unittest import mock


class TestOnboardingCandidatesEndpoint:
    """Tests for GET /api/onboarding/candidates."""

    def test_returns_501_in_docker_mode(self, test_client_docker_mode):
        """Should return 501 in Docker mode."""
        response = test_client_docker_mode.get("/api/onboarding/candidates")
        assert response.status_code == 501

    def test_returns_409_when_drive_mounted(self, test_client):
        """Should return 409 when primary drive is already mounted."""
        with mock.patch(
            "controller.api.onboarding.is_primary_drive_mounted", return_value=True,
        ):
            response = test_client.get("/api/onboarding/candidates")
            assert response.status_code == 409

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

    def test_returns_501_in_docker_mode(self, test_client_docker_mode):
        """Should return 501 in Docker mode."""
        response = test_client_docker_mode.post(
            "/api/onboarding/probe",
            json={"device_path": "/dev/sda1", "fstype": "ext4"},
        )
        assert response.status_code == 501

    def test_returns_409_when_drive_mounted(self, test_client):
        """Should return 409 when primary drive is already mounted."""
        with mock.patch(
            "controller.api.onboarding.is_primary_drive_mounted", return_value=True,
        ):
            response = test_client.post(
                "/api/onboarding/probe",
                json={"device_path": "/dev/sda1", "fstype": "ext4"},
            )
            assert response.status_code == 409

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

    def test_returns_501_in_docker_mode(self, test_client_docker_mode):
        """Should return 501 in Docker mode."""
        response = test_client_docker_mode.post(
            "/api/onboarding/commit",
            json={"device_path": "/dev/sda1", "fstype": "ext4"},
        )
        assert response.status_code == 501

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


class TestOnboardingCancelEndpoint:
    """Tests for POST /api/onboarding/cancel."""

    def test_returns_501_in_docker_mode(self, test_client_docker_mode):
        """Should return 501 in Docker mode."""
        response = test_client_docker_mode.post("/api/onboarding/cancel")
        assert response.status_code == 501

    def test_cancel_success(self, test_client):
        """Should return success on cancel."""
        with mock.patch(
            "controller.api.onboarding.cancel_probe",
            return_value={"success": True},
        ):
            response = test_client.post("/api/onboarding/cancel")
            assert response.status_code == 200
