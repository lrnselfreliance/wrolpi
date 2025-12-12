"""
Unit tests for controller.lib.docker_services module.
"""

from unittest import mock

import pytest

from controller.lib.docker_services import (
    can_manage_containers,
    get_container_status,
    get_all_containers_status,
    start_container,
    stop_container,
    restart_container,
    get_container_logs,
    _get_container_name,
    CONTAINER_PREFIX,
)


class TestCanManageContainers:
    """Tests for can_manage_containers function."""

    def test_returns_false_when_not_docker_mode(self):
        """Should return False when not in Docker mode."""
        with mock.patch("controller.lib.docker_services.is_docker_mode", return_value=False):
            assert can_manage_containers() is False

    def test_returns_false_when_docker_not_available(self):
        """Should return False when docker library not available."""
        with mock.patch("controller.lib.docker_services.is_docker_mode", return_value=True):
            with mock.patch("controller.lib.docker_services.DOCKER_AVAILABLE", False):
                assert can_manage_containers() is False

    def test_returns_false_when_socket_missing(self):
        """Should return False when Docker socket doesn't exist."""
        with mock.patch("controller.lib.docker_services.is_docker_mode", return_value=True):
            with mock.patch("controller.lib.docker_services.DOCKER_AVAILABLE", True):
                with mock.patch("os.path.exists", return_value=False):
                    assert can_manage_containers() is False

    def test_returns_true_when_all_conditions_met(self):
        """Should return True when Docker mode, library, and socket available."""
        with mock.patch("controller.lib.docker_services.is_docker_mode", return_value=True):
            with mock.patch("controller.lib.docker_services.DOCKER_AVAILABLE", True):
                with mock.patch("os.path.exists", return_value=True):
                    assert can_manage_containers() is True


class TestGetContainerName:
    """Tests for _get_container_name function."""

    def test_formats_container_name(self):
        """Should format container name with prefix and suffix."""
        result = _get_container_name("api")
        assert result == f"{CONTAINER_PREFIX}-api-1"

    def test_uses_service_name(self):
        """Should use service name in container name."""
        result = _get_container_name("web")
        assert "web" in result


class TestGetContainerStatus:
    """Tests for get_container_status function."""

    def test_returns_unavailable_when_cannot_manage(self):
        """Should return unavailable when can't manage containers."""
        with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=False):
            result = get_container_status("api")
            assert result["status"] == "unknown"
            assert result["available"] is False

    def test_returns_running_status(self):
        """Should return running status for running container."""
        mock_container = mock.Mock()
        mock_container.status = "running"
        mock_container.attrs = {"NetworkSettings": {"Ports": {"8080/tcp": [{"HostPort": "8081"}]}}}

        mock_client = mock.Mock()
        mock_client.containers.get.return_value = mock_container

        with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=True):
            with mock.patch("controller.lib.docker_services._get_client", return_value=mock_client):
                result = get_container_status("api")
                assert result["status"] == "running"
                assert result["available"] is True

    def test_returns_stopped_for_exited_container(self):
        """Should return stopped for exited container."""
        mock_container = mock.Mock()
        mock_container.status = "exited"
        mock_container.attrs = {"NetworkSettings": {"Ports": {}}}

        mock_client = mock.Mock()
        mock_client.containers.get.return_value = mock_container

        with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=True):
            with mock.patch("controller.lib.docker_services._get_client", return_value=mock_client):
                result = get_container_status("api")
                assert result["status"] == "stopped"


class TestGetAllContainersStatus:
    """Tests for get_all_containers_status function."""

    def test_returns_empty_when_cannot_manage(self):
        """Should return empty list when can't manage containers."""
        with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=False):
            result = get_all_containers_status()
            assert result == []

    def test_returns_container_list(self):
        """Should return list of container statuses."""
        mock_container = mock.Mock()
        mock_container.name = f"{CONTAINER_PREFIX}-api-1"
        mock_container.status = "running"
        mock_container.attrs = {"NetworkSettings": {"Ports": {}}}

        mock_client = mock.Mock()
        mock_client.containers.list.return_value = [mock_container]

        with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=True):
            with mock.patch("controller.lib.docker_services._get_client", return_value=mock_client):
                result = get_all_containers_status()
                assert len(result) == 1
                assert result[0]["name"] == "api"

    def test_db_container_not_viewable(self):
        """Database container should not be viewable (port 5432 is not HTTP)."""
        mock_container = mock.Mock()
        mock_container.name = f"{CONTAINER_PREFIX}-db-1"
        mock_container.status = "running"
        mock_container.attrs = {"NetworkSettings": {"Ports": {"5432/tcp": [{"HostPort": "5432"}]}}}

        mock_client = mock.Mock()
        mock_client.containers.list.return_value = [mock_container]

        with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=True):
            with mock.patch("controller.lib.docker_services._get_client", return_value=mock_client):
                result = get_all_containers_status()
                assert len(result) == 1
                assert result[0]["name"] == "db"
                assert result[0]["viewable"] is False

    def test_api_container_is_viewable(self):
        """API container should be viewable (HTTP service)."""
        mock_container = mock.Mock()
        mock_container.name = f"{CONTAINER_PREFIX}-api-1"
        mock_container.status = "running"
        mock_container.attrs = {"NetworkSettings": {"Ports": {"8081/tcp": [{"HostPort": "8081"}]}}}

        mock_client = mock.Mock()
        mock_client.containers.list.return_value = [mock_container]

        with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=True):
            with mock.patch("controller.lib.docker_services._get_client", return_value=mock_client):
                result = get_all_containers_status()
                assert len(result) == 1
                assert result[0]["name"] == "api"
                assert result[0]["viewable"] is True

    def test_https_container_uses_https(self):
        """Containers with _https suffix should have use_https=True."""
        mock_container = mock.Mock()
        mock_container.name = f"{CONTAINER_PREFIX}-help_https-1"
        mock_container.status = "running"
        mock_container.attrs = {"NetworkSettings": {"Ports": {"8086/tcp": [{"HostPort": "8086"}]}}}

        mock_client = mock.Mock()
        mock_client.containers.list.return_value = [mock_container]

        with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=True):
            with mock.patch("controller.lib.docker_services._get_client", return_value=mock_client):
                result = get_all_containers_status()
                assert len(result) == 1
                assert result[0]["name"] == "help_https"
                assert result[0]["use_https"] is True

    def test_non_https_container_uses_http(self):
        """Containers without _https suffix should have use_https=False."""
        mock_container = mock.Mock()
        mock_container.name = f"{CONTAINER_PREFIX}-api-1"
        mock_container.status = "running"
        mock_container.attrs = {"NetworkSettings": {"Ports": {"8081/tcp": [{"HostPort": "8081"}]}}}

        mock_client = mock.Mock()
        mock_client.containers.list.return_value = [mock_container]

        with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=True):
            with mock.patch("controller.lib.docker_services._get_client", return_value=mock_client):
                result = get_all_containers_status()
                assert len(result) == 1
                assert result[0]["name"] == "api"
                assert result[0].get("use_https", False) is False

    def test_web_container_uses_https(self):
        """Web container (nginx proxy) should have use_https=True."""
        mock_container = mock.Mock()
        mock_container.name = f"{CONTAINER_PREFIX}-web-1"
        mock_container.status = "running"
        mock_container.attrs = {"NetworkSettings": {"Ports": {"443/tcp": [{"HostPort": "8443"}]}}}

        mock_client = mock.Mock()
        mock_client.containers.list.return_value = [mock_container]

        with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=True):
            with mock.patch("controller.lib.docker_services._get_client", return_value=mock_client):
                result = get_all_containers_status()
                assert len(result) == 1
                assert result[0]["name"] == "web"
                assert result[0]["use_https"] is True

    def test_filters_by_prefix(self):
        """Should only return containers with correct prefix."""
        mock_container1 = mock.Mock()
        mock_container1.name = f"{CONTAINER_PREFIX}-api-1"
        mock_container1.status = "running"
        mock_container1.attrs = {"NetworkSettings": {"Ports": {}}}

        mock_container2 = mock.Mock()
        mock_container2.name = "other-container"
        mock_container2.status = "running"
        mock_container2.attrs = {"NetworkSettings": {"Ports": {}}}

        mock_client = mock.Mock()
        mock_client.containers.list.return_value = [mock_container1, mock_container2]

        with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=True):
            with mock.patch("controller.lib.docker_services._get_client", return_value=mock_client):
                result = get_all_containers_status()
                assert len(result) == 1
                assert result[0]["name"] == "api"


class TestContainerActions:
    """Tests for container action functions."""

    @pytest.mark.parametrize("func", [
        start_container,
        stop_container,
        restart_container,
    ])
    def test_returns_error_when_cannot_manage(self, func):
        """Should return error when can't manage containers."""
        with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=False):
            result = func("api")
            assert result["success"] is False

    @pytest.mark.parametrize("func,method_name,expected_action,call_kwargs", [
        (start_container, "start", "start", {}),
        (stop_container, "stop", "stop", {"timeout": 30}),
        (restart_container, "restart", "restart", {"timeout": 30}),
    ])
    def test_performs_container_action(self, func, method_name, expected_action, call_kwargs):
        """Should perform the correct container action."""
        mock_container = mock.Mock()
        mock_client = mock.Mock()
        mock_client.containers.get.return_value = mock_container

        with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=True):
            with mock.patch("controller.lib.docker_services._get_client", return_value=mock_client):
                result = func("api")
                method = getattr(mock_container, method_name)
                if call_kwargs:
                    method.assert_called_once_with(**call_kwargs)
                else:
                    method.assert_called_once()
                assert result["success"] is True
                assert result["action"] == expected_action


class TestGetContainerLogs:
    """Tests for get_container_logs function."""

    def test_returns_error_when_cannot_manage(self):
        """Should return error when can't manage containers."""
        with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=False):
            result = get_container_logs("api")
            assert "error" in result

    def test_returns_logs(self):
        """Should return container logs."""
        mock_container = mock.Mock()
        mock_container.logs.return_value = b"log line 1\nlog line 2"

        mock_client = mock.Mock()
        mock_client.containers.get.return_value = mock_container

        with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=True):
            with mock.patch("controller.lib.docker_services._get_client", return_value=mock_client):
                result = get_container_logs("api", lines=50)
                mock_container.logs.assert_called_once_with(tail=50)
                assert result["logs"] == "log line 1\nlog line 2"
                assert result["service"] == "api"
                assert result["lines"] == 50
