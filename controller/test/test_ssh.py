"""
Unit tests for controller.lib.ssh (runtime start/stop, fail open).
"""

from unittest import mock

import pytest

from controller.lib import ssh as ssh_lib


def _completed(returncode=0, stdout="", stderr=""):
    return mock.Mock(returncode=returncode, stdout=stdout, stderr=stderr)


class TestResolveSshUnit:
    def test_prefers_ssh_over_sshd(self):
        def show_side_effect(*args, **kwargs):
            # systemctl show -p LoadState --value <unit>
            unit = args[-1] if args else ""
            if unit == "ssh":
                return _completed(stdout="loaded\n")
            return _completed(stdout="not-found\n")

        with mock.patch.object(ssh_lib, "_systemctl", side_effect=show_side_effect):
            assert ssh_lib.resolve_ssh_unit() == "ssh"

    def test_falls_back_to_sshd(self):
        def show_side_effect(*args, **kwargs):
            unit = args[-1] if args else ""
            if unit == "sshd":
                return _completed(stdout="loaded\n")
            return _completed(stdout="not-found\n")

        with mock.patch.object(ssh_lib, "_systemctl", side_effect=show_side_effect):
            assert ssh_lib.resolve_ssh_unit() == "sshd"

    def test_none_when_missing(self):
        with mock.patch.object(ssh_lib, "_systemctl", return_value=_completed(stdout="not-found\n")):
            assert ssh_lib.resolve_ssh_unit() is None


class TestGetSshStatusDict:
    def test_docker_mode_unavailable(self, monkeypatch):
        monkeypatch.setenv("DOCKERIZED", "true")
        # Reload config check via is_docker_mode patch is safer
        with mock.patch("controller.lib.ssh.is_docker_mode", return_value=True):
            status = ssh_lib.get_ssh_status_dict()
        assert status["available"] is False
        assert status["enabled"] is False
        assert "Docker" in status["reason"]

    def test_running(self):
        with mock.patch.object(ssh_lib, "resolve_ssh_unit", return_value="ssh"), \
             mock.patch.object(ssh_lib, "_is_active", return_value=True), \
             mock.patch.object(ssh_lib, "_is_enabled_at_boot", return_value=True), \
             mock.patch("controller.lib.ssh.is_docker_mode", return_value=False):
            status = ssh_lib.get_ssh_status_dict()
        assert status == {
            "enabled": True,
            "enabled_at_boot": True,
            "available": True,
            "reason": None,
            "unit": "ssh",
        }


class TestStartStopSsh:
    def test_start_uses_start_not_enable(self):
        calls = []

        def sysctl(*args, **kwargs):
            calls.append(args)
            return _completed()

        with mock.patch("controller.lib.ssh.is_docker_mode", return_value=False), \
             mock.patch.object(ssh_lib, "resolve_ssh_unit", return_value="ssh"), \
             mock.patch.object(ssh_lib, "_systemctl", side_effect=sysctl):
            result = ssh_lib.start_ssh()

        assert result["success"] is True
        assert ("start", "ssh") in calls
        assert not any(c[0] == "enable" for c in calls)

    def test_stop_uses_stop_not_disable(self):
        calls = []

        def sysctl(*args, **kwargs):
            calls.append(args)
            return _completed()

        with mock.patch("controller.lib.ssh.is_docker_mode", return_value=False), \
             mock.patch.object(ssh_lib, "resolve_ssh_unit", return_value="ssh"), \
             mock.patch.object(ssh_lib, "_systemctl", side_effect=sysctl):
            result = ssh_lib.stop_ssh()

        assert result["success"] is True
        assert ("stop", "ssh") in calls
        assert not any(c[0] == "disable" for c in calls)

    def test_aliases_match_start_stop(self):
        assert ssh_lib.enable_ssh is ssh_lib.start_ssh
        assert ssh_lib.disable_ssh is ssh_lib.stop_ssh
