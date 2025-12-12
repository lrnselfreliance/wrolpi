"""
Integration tests for Controller disks API endpoints.
"""

from unittest import mock


class TestDisksListEndpoint:
    """Tests for /api/disks endpoint."""

    def test_returns_501_in_docker_mode(self, test_client_docker_mode):
        """Should return 501 in Docker mode."""
        response = test_client_docker_mode.get("/api/disks")
        assert response.status_code == 501

    def test_returns_list_in_native_mode(self, test_client):
        """Should return list of disks in native mode."""
        with mock.patch("controller.api.disks.get_block_devices", return_value=[]):
            response = test_client.get("/api/disks")
            assert response.status_code == 200
            assert isinstance(response.json(), list)


class TestMountsEndpoint:
    """Tests for /api/disks/mounts endpoint."""

    def test_returns_501_in_docker_mode(self, test_client_docker_mode):
        """Should return 501 in Docker mode."""
        response = test_client_docker_mode.get("/api/disks/mounts")
        assert response.status_code == 501

    def test_returns_mounts(self, test_client):
        """Should return current mounts."""
        mock_mounts = [{"mount_point": "/media/wrolpi", "device": "/dev/sda1"}]
        with mock.patch("controller.api.disks.get_mounts", return_value=mock_mounts):
            response = test_client.get("/api/disks/mounts")
            assert response.status_code == 200
            assert response.json() == mock_mounts


class TestMountEndpoint:
    """Tests for /api/disks/mount endpoint."""

    def test_returns_501_in_docker_mode(self, test_client_docker_mode):
        """Should return 501 in Docker mode."""
        response = test_client_docker_mode.post(
            "/api/disks/mount",
            json={"device": "/dev/sda1", "mount_point": "/media/test"}
        )
        assert response.status_code == 501

    def test_mounts_drive_successfully(self, test_client):
        """Should mount drive successfully."""
        with mock.patch(
                "controller.api.disks.mount_drive",
                return_value={"success": True, "mount_point": "/media/test"}
        ):
            response = test_client.post(
                "/api/disks/mount",
                json={"device": "/dev/sda1", "mount_point": "/media/test"}
            )
            assert response.status_code == 200
            assert response.json()["success"] is True

    def test_returns_500_on_failure(self, test_client):
        """Should return 500 on mount failure."""
        with mock.patch(
                "controller.api.disks.mount_drive",
                return_value={"success": False, "error": "Mount failed"}
        ):
            response = test_client.post(
                "/api/disks/mount",
                json={"device": "/dev/sda1", "mount_point": "/media/test"}
            )
            assert response.status_code == 500


class TestUnmountEndpoint:
    """Tests for /api/disks/unmount endpoint."""

    def test_returns_501_in_docker_mode(self, test_client_docker_mode):
        """Should return 501 in Docker mode."""
        response = test_client_docker_mode.post(
            "/api/disks/unmount",
            json={"mount_point": "/media/test"}
        )
        assert response.status_code == 501

    def test_unmounts_drive_successfully(self, test_client):
        """Should unmount drive successfully."""
        with mock.patch(
                "controller.api.disks.unmount_drive",
                return_value={"success": True, "mount_point": "/media/test"}
        ):
            response = test_client.post(
                "/api/disks/unmount",
                json={"mount_point": "/media/test"}
            )
            assert response.status_code == 200


class TestFstabEndpoints:
    """Tests for /api/disks/fstab endpoints."""

    def test_list_fstab_returns_501_in_docker(self, test_client_docker_mode):
        """Should return 501 in Docker mode."""
        response = test_client_docker_mode.get("/api/disks/fstab")
        assert response.status_code == 501

    def test_list_fstab_returns_entries(self, test_client):
        """Should return fstab entries."""
        mock_entries = [{"mount_point": "/media/wrolpi", "device": "UUID=1234"}]
        with mock.patch("controller.api.disks.get_wrolpi_fstab_entries", return_value=mock_entries):
            response = test_client.get("/api/disks/fstab")
            assert response.status_code == 200
            assert response.json() == mock_entries

    def test_add_fstab_returns_501_in_docker(self, test_client_docker_mode):
        """Should return 501 in Docker mode."""
        response = test_client_docker_mode.post(
            "/api/disks/fstab",
            json={"device": "/dev/sda1", "mount_point": "/media/test", "fstype": "ext4"}
        )
        assert response.status_code == 501

    def test_add_fstab_entry(self, test_client):
        """Should add fstab entry."""
        with mock.patch(
                "controller.api.disks.add_fstab_entry",
                return_value={"success": True, "mount_point": "/media/test"}
        ):
            response = test_client.post(
                "/api/disks/fstab",
                json={"device": "/dev/sda1", "mount_point": "/media/test", "fstype": "ext4"}
            )
            assert response.status_code == 200

    def test_delete_fstab_returns_501_in_docker(self, test_client_docker_mode):
        """Should return 501 in Docker mode."""
        response = test_client_docker_mode.delete("/api/disks/fstab/media/test")
        assert response.status_code == 501


class TestSmartEndpoints:
    """Tests for /api/disks/smart endpoints."""

    def test_list_smart_returns_501_in_docker(self, test_client_docker_mode):
        """Should return 501 in Docker mode."""
        response = test_client_docker_mode.get("/api/disks/smart")
        assert response.status_code == 501

    def test_list_smart_when_not_available(self, test_client):
        """Should return unavailable when SMART not available."""
        with mock.patch("controller.api.disks.is_smart_available", return_value=False):
            response = test_client.get("/api/disks/smart")
            assert response.status_code == 200
            data = response.json()
            assert data["available"] is False

    def test_list_smart_returns_drives(self, test_client):
        """Should return SMART data for all drives."""
        mock_drives = [{"device": "sda", "assessment": "PASS"}]
        with mock.patch("controller.api.disks.is_smart_available", return_value=True):
            with mock.patch("controller.api.disks.get_all_smart_status", return_value=mock_drives):
                response = test_client.get("/api/disks/smart")
                assert response.status_code == 200
                data = response.json()
                assert data["available"] is True
                assert len(data["drives"]) == 1


class TestOpenAPIIncludesDisksEndpoints:
    """Tests that OpenAPI documentation includes disks endpoints."""

    def test_openapi_has_disks_paths(self, test_client):
        """OpenAPI schema should include disks paths."""
        response = test_client.get("/openapi.json")
        data = response.json()
        assert "/api/disks" in data["paths"]
        assert "/api/disks/mounts" in data["paths"]
        assert "/api/disks/mount" in data["paths"]
        assert "/api/disks/unmount" in data["paths"]
        assert "/api/disks/fstab" in data["paths"]
        assert "/api/disks/smart" in data["paths"]
