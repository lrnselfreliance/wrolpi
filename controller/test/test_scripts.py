"""
Unit tests for controller.lib.scripts module.
"""

import json
import subprocess
import time
from unittest import mock

import pytest

from controller.lib.scripts import (
    _get_service_timing,
    AVAILABLE_SCRIPTS,
    get_current_branch,
    get_script_output,
    get_script_result,
    get_script_status,
    list_available_scripts,
    start_script,
)


class TestGetCurrentBranch:
    """Tests for get_current_branch function."""

    def test_returns_branch_name(self):
        """Should return the branch name from `git branch --show-current`.

        `git rev-parse --abbrev-ref HEAD` must not be used: it reports "heads/release" when a
        stale `release` tag exists alongside the `release` branch.
        """
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "release\n"

        with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
            assert get_current_branch() == "release"
        cmd = mock_run.call_args[0][0]
        assert "--show-current" in cmd
        assert "--abbrev-ref" not in cmd

    def test_detached_head_defaults_to_release(self):
        """A detached HEAD (empty output) should default to 'release'."""
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "\n"

        with mock.patch("subprocess.run", return_value=mock_result):
            assert get_current_branch() == "release"

    def test_git_failure_returns_none(self):
        """A failing git command should return None."""
        mock_result = mock.MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""

        with mock.patch("subprocess.run", return_value=mock_result):
            assert get_current_branch() is None


class TestAvailableScripts:
    """Tests for AVAILABLE_SCRIPTS constant."""

    def test_repair_script_exists(self):
        """Should have a repair script defined."""
        assert "repair" in AVAILABLE_SCRIPTS

    def test_repair_script_has_required_fields(self):
        """Repair script should have all required fields."""
        repair = AVAILABLE_SCRIPTS["repair"]
        assert "name" in repair
        assert "display_name" in repair
        assert "description" in repair
        assert "service_name" in repair
        assert "warnings" in repair

    def test_repair_script_has_warnings(self):
        """Repair script should have warnings about its effects."""
        repair = AVAILABLE_SCRIPTS["repair"]
        assert len(repair["warnings"]) > 0

    def test_help_script_exists(self):
        """Should have a help (diagnostics) script defined."""
        assert "help" in AVAILABLE_SCRIPTS
        help_script = AVAILABLE_SCRIPTS["help"]
        assert help_script["service_name"] == "wrolpi-help-script.service"
        # help.sh is read-only, so it needs no warnings.
        assert help_script["warnings"] == []


class TestListAvailableScripts:
    """Tests for list_available_scripts function."""

    def test_returns_list(self):
        """Should return a list."""
        result = list_available_scripts()
        assert isinstance(result, list)

    def test_returns_scripts_with_required_fields(self):
        """Each script should have required fields."""
        result = list_available_scripts()
        for script in result:
            assert "name" in script
            assert "display_name" in script
            assert "description" in script
            assert "warnings" in script
            assert "available" in script

    def test_scripts_unavailable_in_docker_mode(self):
        """Scripts should be marked unavailable in Docker mode."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=True):
            result = list_available_scripts()
            for script in result:
                assert script["available"] is False

    def test_scripts_available_when_not_docker(self):
        """Scripts should be available when not in Docker mode."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            result = list_available_scripts()
            for script in result:
                assert script["available"] is True


class TestGetScriptStatus:
    """Tests for get_script_status function."""

    def test_returns_dict(self):
        """Should return a dict."""
        result = get_script_status()
        assert isinstance(result, dict)

    def test_has_running_field(self):
        """Should always have running field."""
        result = get_script_status()
        assert "running" in result

    def test_returns_not_running_in_docker_mode(self):
        """Should return not running in Docker mode."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=True):
            result = get_script_status()
            assert result["running"] is False

    def test_handles_systemctl_not_found(self):
        """Should handle systemctl not being available."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
                result = get_script_status()
                assert result["running"] is False

    def test_handles_timeout(self):
        """Should handle subprocess timeout."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("systemctl", 5)):
                result = get_script_status()
                assert result["running"] is False

    def test_returns_running_when_service_activating(self):
        """Should return running when service is activating."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            mock_result = mock.Mock()
            mock_result.stdout = "activating\n"
            mock_result.returncode = 0
            with mock.patch("subprocess.run", return_value=mock_result):
                with mock.patch("controller.lib.scripts._get_service_timing", return_value=(None, None)):
                    result = get_script_status()
                    assert result["running"] is True
                    # The first script checked reports as running because every systemctl call is mocked.
                    assert result["script_name"] == next(iter(AVAILABLE_SCRIPTS))

    def test_returns_not_running_when_service_inactive(self):
        """Should return not running when service is inactive."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            mock_result = mock.Mock()
            mock_result.stdout = "inactive\n"
            mock_result.returncode = 3
            with mock.patch("subprocess.run", return_value=mock_result):
                result = get_script_status()
                assert result["running"] is False


class TestStartScript:
    """Tests for start_script function."""

    def test_returns_error_in_docker_mode(self):
        """Should return error in Docker mode."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=True):
            result = start_script("repair")
            assert result["success"] is False
            assert "Docker" in result.get("error", "")

    def test_returns_error_for_unknown_script(self):
        """Should return error for unknown script."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            result = start_script("nonexistent")
            assert result["success"] is False
            assert "Unknown" in result.get("error", "")

    def test_returns_error_if_already_running(self):
        """Should return error if script is already running."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.scripts.get_script_status", return_value={
                "running": True,
                "script_name": "repair",
            }):
                result = start_script("repair")
                assert result["success"] is False
                assert "already running" in result.get("error", "").lower()

    def test_returns_error_if_another_script_running(self):
        """Should return error if another script is running."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.scripts.get_script_status", return_value={
                "running": True,
                "script_name": "other",
            }):
                result = start_script("repair")
                assert result["success"] is False
                assert "another script" in result.get("error", "").lower()

    def test_handles_systemctl_not_found(self):
        """Should handle systemctl not being available."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.scripts.get_script_status", return_value={"running": False}):
                with mock.patch("subprocess.Popen", side_effect=FileNotFoundError()):
                    result = start_script("repair")
                    assert result["success"] is False
                    assert "not found" in result.get("error", "").lower()

    def test_starts_service_successfully(self):
        """Should start service successfully."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.scripts.get_script_status", return_value={"running": False}):
                mock_popen = mock.Mock()
                with mock.patch("subprocess.Popen", return_value=mock_popen) as mock_p:
                    result = start_script("repair")
                    assert result["success"] is True
                    assert "started" in result.get("message", "").lower()
                    # Verify correct command was called
                    mock_p.assert_called_once()
                    call_args = mock_p.call_args[0][0]
                    assert "systemctl" in call_args
                    assert "start" in call_args
                    assert "wrolpi-repair.service" in call_args


    def _start_upgrade(self, tmp_path, params, current_branch="master"):
        """Start the upgrade script with its env file in `tmp_path`.  Returns (result, env file, Popen mock)."""
        env_file = tmp_path / "wrolpi-upgrade.env"
        with mock.patch.dict(AVAILABLE_SCRIPTS["upgrade"], {"env_file": str(env_file)}), \
                mock.patch("controller.lib.scripts.is_docker_mode", return_value=False), \
                mock.patch("controller.lib.scripts.get_script_status", return_value={"running": False}), \
                mock.patch("controller.lib.scripts.get_current_branch", return_value=current_branch), \
                mock.patch("subprocess.Popen") as popen:
            result = start_script("upgrade", params=params)
        return result, env_file, popen

    def test_upgrade_without_branch_writes_current_branch(self, tmp_path):
        """The upgrade service reads BRANCH from its env file, and fails to start without the file; upgrade.sh
        removes it when it finishes.  With no branch, upgrade the current one, as upgrade.sh does."""
        for params in (None, {}, {"branch": ""}):
            result, env_file, popen = self._start_upgrade(tmp_path, params)
            assert result["success"] is True, params
            assert env_file.read_text() == "BRANCH=master\n", params
            popen.assert_called_once()
            env_file.unlink()

    def test_upgrade_replaces_stale_env_file(self, tmp_path):
        """A file left by an interrupted upgrade does not choose the branch."""
        (tmp_path / "wrolpi-upgrade.env").write_text("BRANCH=old\n")
        result, env_file, _ = self._start_upgrade(tmp_path, None, current_branch="release")
        assert result["success"] is True
        assert env_file.read_text() == "BRANCH=release\n"

        result, env_file, _ = self._start_upgrade(tmp_path, {"branch": "master"}, current_branch="release")
        assert env_file.read_text() == "BRANCH=master\n"

    def test_unknown_param_is_rejected(self, tmp_path):
        """A misspelled parameter is an error, not silently ignored."""
        result, env_file, popen = self._start_upgrade(tmp_path, {"brnch": "master"})
        assert result["success"] is False
        assert "brnch" in result["error"]
        assert not env_file.exists()
        popen.assert_not_called()


    @pytest.mark.parametrize("branch", [
        "master\nEVIL=1", "master\rEVIL=1", "-b", "a..b", "a b", "foo.lock", "foo/", "/foo", "a//b", "a$b", "x" * 256,
    ])
    def test_invalid_branch_is_rejected(self, tmp_path, branch):
        """The branch is written into the systemd env file and passed to `upgrade.sh -b`; a branch name git would
        refuse, or one that could add a line to the env file, never starts an upgrade."""
        result, env_file, popen = self._start_upgrade(tmp_path, {"branch": branch})
        assert result["success"] is False
        assert "branch" in result["error"].lower()
        assert not env_file.exists()
        popen.assert_not_called()

    @pytest.mark.parametrize("branch", ["master", "release", "feature/new-thing", "v1.2_fix"])
    def test_valid_branch_is_written(self, tmp_path, branch):
        result, env_file, popen = self._start_upgrade(tmp_path, {"branch": branch})
        assert result["success"] is True
        assert env_file.read_text() == f"BRANCH={branch}\n"
        popen.assert_called_once()


class TestGetScriptOutput:
    """Tests for get_script_output function."""

    def test_returns_docker_message_in_docker_mode(self):
        """Should return Docker not available message in Docker mode."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=True):
            result = get_script_output("repair")
            assert "Docker" in result.get("output", "")

    def test_returns_error_for_unknown_script(self):
        """Should return error for unknown script."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            result = get_script_output("nonexistent")
            assert "Unknown" in result.get("output", "")

    def test_handles_journalctl_not_found(self):
        """Should handle journalctl not being available."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
                result = get_script_output("repair")
                assert "not found" in result.get("output", "").lower()

    def test_handles_timeout(self):
        """Should handle subprocess timeout."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("journalctl", 10)):
                result = get_script_output("repair")
                assert "Timeout" in result.get("output", "")

    def test_returns_log_output(self):
        """Should return log output from journalctl."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            mock_result = mock.Mock()
            mock_result.stdout = "Log line 1\nLog line 2\n"
            mock_result.returncode = 0
            with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
                result = get_script_output("repair", lines=50)
                assert "Log line 1" in result.get("output", "")
                assert result["lines"] == 50
                assert result["script_name"] == "repair"
                # Verify correct command
                call_args = mock_run.call_args[0][0]
                assert "journalctl" in call_args
                assert "-u" in call_args
                assert "wrolpi-repair.service" in call_args
                assert "-n" in call_args
                assert "50" in call_args


class TestGetServiceTiming:

    def test_elapsed_is_independent_of_local_timezone(self):
        """systemd prints timestamps in local time; elapsed must not be off by the UTC offset."""
        started = time.time() - 90
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=f"ExecMainStartTimestamp=@{started:.6f}\n")
        with mock.patch("controller.lib.scripts.subprocess.run", return_value=completed) as run:
            started_at, elapsed = _get_service_timing("wrolpi-upgrade.service")
        assert "--timestamp=unix" in run.call_args.args[0]
        assert 89 <= elapsed <= 91
        assert started_at.endswith("+00:00")

    def test_not_started(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="ExecMainStartTimestamp=\n")
        with mock.patch("controller.lib.scripts.subprocess.run", return_value=completed):
            assert _get_service_timing("wrolpi-upgrade.service") == (None, None)


def _systemctl_show(stdout: str):
    return mock.Mock(returncode=0, stdout=stdout)


# systemd's message IDs for a unit that ended cleanly or failed.
UNIT_SUCCESS = "7ad2d189f7e94e70a38c781354912448"
UNIT_FAILURE = "d9b373ed55a64feb8242e02dbe79a49c"


def _fake_run(systemctl_stdout: str, journal_stdout: str = ""):
    """Answer `systemctl show` and `journalctl` calls with their own output."""

    def run(args, **kwargs):
        stdout = journal_stdout if args[0] == "journalctl" else systemctl_stdout
        return mock.Mock(returncode=0, stdout=stdout)

    return run


def _journal_entry(message_id: str, realtime_us: int) -> str:
    return json.dumps({"MESSAGE_ID": message_id, "__REALTIME_TIMESTAMP": str(realtime_us)}) + "\n"


class TestGetScriptResult:
    """How the last run of a script ended, read from systemd."""

    def test_failed_run(self):
        """An upgrade that exited non-zero is reported as failed, with its exit status and when it finished."""
        stdout = "Result=exit-code\nExecMainStatus=5\nActiveState=failed\nExecMainExitTimestamp=@1794151352.5\n"
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False), \
                mock.patch("controller.lib.scripts.subprocess.run", return_value=_systemctl_show(stdout)) as run:
            result = get_script_result("upgrade")
        assert result == {
            "script_name": "upgrade",
            "running": False,
            "finished": True,
            "success": False,
            "result": "exit-code",
            "exit_status": 5,
            "finished_at": "2026-11-08T15:22:32.500000+00:00",
        }
        assert "wrolpi-upgrade.service" in run.call_args[0][0]

    def test_successful_run(self):
        stdout = "Result=success\nExecMainStatus=0\nActiveState=inactive\nExecMainExitTimestamp=@1762615352\n"
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False), \
                mock.patch("controller.lib.scripts.subprocess.run", return_value=_systemctl_show(stdout)):
            result = get_script_result("upgrade")
        assert result["finished"] is True
        assert result["success"] is True
        assert result["exit_status"] == 0

    def test_running(self):
        """A run in progress has not finished, so it has neither succeeded nor failed."""
        stdout = "Result=success\nExecMainStatus=0\nActiveState=activating\nExecMainExitTimestamp=\n"
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False), \
                mock.patch("controller.lib.scripts.subprocess.run", return_value=_systemctl_show(stdout)):
            result = get_script_result("upgrade")
        assert result["running"] is True
        assert result["finished"] is False
        assert result["success"] is None
        assert result["finished_at"] is None

    def test_failed_run_after_daemon_reload(self):
        """An upgrade reloads systemd, which clears the run's timestamps but keeps its Result and exit status. The
        journal still has when it ended."""
        stdout = "Result=exit-code\nExecMainStatus=5\nActiveState=failed\nExecMainExitTimestamp=\n"
        journal = _journal_entry(UNIT_FAILURE, 1794151352500000)
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False), \
                mock.patch("controller.lib.scripts.subprocess.run", side_effect=_fake_run(stdout, journal)):
            result = get_script_result("upgrade")
        assert result["running"] is False
        assert result["finished"] is True
        assert result["success"] is False
        assert result["exit_status"] == 5
        assert result["finished_at"] == "2026-11-08T15:22:32.500000+00:00"

    def test_successful_run_after_daemon_reload(self):
        """A clean run whose timestamps were cleared looks like a service that never ran, so the journal decides."""
        stdout = "Result=success\nExecMainStatus=0\nActiveState=inactive\nExecMainExitTimestamp=\n"
        journal = _journal_entry(UNIT_SUCCESS, 1794151352500000)
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False), \
                mock.patch("controller.lib.scripts.subprocess.run", side_effect=_fake_run(stdout, journal)) as run:
            result = get_script_result("upgrade")
        assert result["running"] is False
        assert result["finished"] is True
        assert result["success"] is True
        assert result["finished_at"] == "2026-11-08T15:22:32.500000+00:00"
        journal_args = run.call_args_list[-1].args[0]
        assert journal_args[0] == "journalctl"
        assert "UNIT=wrolpi-upgrade.service" in journal_args

    def test_never_run(self):
        """A service that has never run has no result, and nothing in the journal."""
        stdout = "Result=success\nExecMainStatus=0\nActiveState=inactive\nExecMainExitTimestamp=\n"
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False), \
                mock.patch("controller.lib.scripts.subprocess.run", side_effect=_fake_run(stdout, "")):
            result = get_script_result("upgrade")
        assert result["finished"] is False
        assert result["success"] is None
        assert result["finished_at"] is None

    def test_journal_unreadable(self):
        """Without the journal, a clean run with cleared timestamps is reported as not known to have finished."""
        stdout = "Result=success\nExecMainStatus=0\nActiveState=inactive\nExecMainExitTimestamp=\n"

        def run(args, **kwargs):
            if args[0] == "journalctl":
                raise FileNotFoundError
            return _systemctl_show(stdout)

        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False), \
                mock.patch("controller.lib.scripts.subprocess.run", side_effect=run):
            result = get_script_result("upgrade")
        assert result["running"] is False
        assert result["finished"] is False
        assert result["success"] is None

    def test_systemctl_missing(self):
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False), \
                mock.patch("controller.lib.scripts.subprocess.run", side_effect=FileNotFoundError):
            result = get_script_result("upgrade")
        assert result["finished"] is False
        assert result["success"] is None

    def test_unknown_script(self):
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            assert get_script_result("nonexistent") is None
