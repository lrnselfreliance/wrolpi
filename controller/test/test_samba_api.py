"""
Integration tests for Controller Samba API endpoints.
"""


class TestSambaStatusEndpoint:
    """Tests for /api/samba/status endpoint."""

    def test_returns_200(self, test_client):
        response = test_client.get("/api/samba/status")
        assert response.status_code == 200

    def test_returns_expected_fields(self, test_client):
        response = test_client.get("/api/samba/status")
        data = response.json()
        assert "enabled" in data
        assert "available" in data
        assert "shares" in data


class TestSambaShareAddEndpoint:
    """Tests for POST /api/samba/shares endpoint."""

    def test_rejects_invalid_name(self, test_client):
        response = test_client.post("/api/samba/shares", json={
            "name": "bad/name",
            "path": "/media/wrolpi",
        })
        assert response.status_code == 400


class TestSambaShareRemoveEndpoint:
    """Tests for DELETE /api/samba/shares/{name} endpoint."""

    def test_returns_404_for_missing_share(self, test_client):
        response = test_client.delete("/api/samba/shares/nonexistent")
        assert response.status_code == 404
