"""
Unit tests for controller.lib.desktop (runtime start/stop, fail open).
"""

from unittest import mock

from controller.lib import desktop as desktop_lib


def _completed(returncode=0, stdout="", stderr=""):
    return mock.Mock(returncode=returncode, stdout=stdout, stderr=stderr)


class TestResolveDisplayManager:
    def test_prefers_display_manager_alias(self):
        def show_side_effect(*args, **kwargs):
            unit = args[-1] if args else ""
            if unit == "display-manager":
                return _completed(stdout="loaded\n")
            return _completed(stdout="not-found\n")

        with mock.patch.object(desktop_lib, "_systemctl", side_effect=show_side_effect):
            assert desktop_lib.resolve_display_manager_unit() == "display-manager"

    def test_falls_back_to_lightdm(self):
        def show_side_effect(*args, **kwargs):
            unit = args[-1] if args else ""
            if unit == "lightdm":
                return _completed(stdout="loaded\n")
            return _completed(stdout="not-found\n")

        with mock.patch.object(desktop_lib, "_systemctl", side_effect=show_side_effect):
            assert desktop_lib.resolve_display_manager_unit() == "lightdm"


class TestGetDesktopStatusDict:
    def test_docker_mode_unavailable(self):
        with mock.patch("controller.lib.desktop.is_docker_mode", return_value=True):
            status = desktop_lib.get_desktop_status_dict()
        assert status["available"] is False
        assert "Docker" in status["reason"]

    def test_running_with_default_target(self):
        with mock.patch("controller.lib.desktop.is_docker_mode", return_value=False), \
             mock.patch.object(desktop_lib, "resolve_display_manager_unit", return_value="lightdm"), \
             mock.patch.object(desktop_lib, "_is_active", return_value=True), \
             mock.patch.object(desktop_lib, "get_default_target", return_value="graphical.target"):
            status = desktop_lib.get_desktop_status_dict()
        assert status["enabled"] is True
        assert status["available"] is True
        assert status["unit"] == "lightdm"
        assert status["default_target"] == "graphical.target"


class TestStartStopDesktop:
    def test_start_uses_start_not_set_default(self):
        calls = []

        def sysctl(*args, **kwargs):
            calls.append(args)
            return _completed()

        with mock.patch("controller.lib.desktop.is_docker_mode", return_value=False), \
             mock.patch.object(desktop_lib, "resolve_display_manager_unit", return_value="lightdm"), \
             mock.patch.object(desktop_lib, "_systemctl", side_effect=sysctl):
            result = desktop_lib.start_desktop()

        assert result["success"] is True
        assert ("start", "lightdm") in calls
        assert not any(c and c[0] == "set-default" for c in calls)
        assert not any(c and c[0] == "isolate" for c in calls)

    def test_stop_uses_stop_not_set_default(self):
        calls = []

        def sysctl(*args, **kwargs):
            calls.append(args)
            return _completed()

        with mock.patch("controller.lib.desktop.is_docker_mode", return_value=False), \
             mock.patch.object(desktop_lib, "resolve_display_manager_unit", return_value="lightdm"), \
             mock.patch.object(desktop_lib, "_systemctl", side_effect=sysctl):
            result = desktop_lib.stop_desktop()

        assert result["success"] is True
        assert ("stop", "lightdm") in calls
        assert not any(c and c[0] == "set-default" for c in calls)
        assert not any(c and c[0] == "disable" for c in calls)

    def test_aliases_match_start_stop(self):
        assert desktop_lib.enable_desktop is desktop_lib.start_desktop
        assert desktop_lib.disable_desktop is desktop_lib.stop_desktop
