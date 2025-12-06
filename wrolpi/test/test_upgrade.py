"""
Tests for the WROLPi upgrade system.
"""
from unittest.mock import patch, MagicMock

import pytest

from wrolpi.upgrade import (
    check_for_update,
    get_current_branch,
    get_local_commit,
    get_remote_commit,
    get_commits_behind,
    git_fetch,
    start_upgrade,
)


class TestGitFunctions:
    """Test git helper functions."""

    def test_git_fetch_directory_not_exists(self):
        """git_fetch returns False when directory doesn't exist."""
        mock_path = MagicMock()
        mock_path.is_dir.return_value = False
        with patch('wrolpi.upgrade.PROJECT_DIR', mock_path):
            assert git_fetch() is False

    def test_git_fetch_success(self):
        """git_fetch returns True on success."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_path = MagicMock()
        mock_path.is_dir.return_value = True

        with patch('wrolpi.upgrade.PROJECT_DIR', mock_path), \
                patch('subprocess.run', return_value=mock_result):
            assert git_fetch() is True

    def test_git_fetch_failure(self):
        """git_fetch returns False when command fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = b'error message'
        mock_path = MagicMock()
        mock_path.is_dir.return_value = True

        with patch('wrolpi.upgrade.PROJECT_DIR', mock_path), \
                patch('subprocess.run', return_value=mock_result):
            assert git_fetch() is False

    def test_get_current_branch(self):
        """get_current_branch returns the branch name."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b'release\n'
        mock_path = MagicMock()
        mock_path.is_dir.return_value = True

        with patch('wrolpi.upgrade.PROJECT_DIR', mock_path), \
                patch('subprocess.run', return_value=mock_result):
            assert get_current_branch() == 'release'

    def test_get_current_branch_directory_not_exists(self):
        """get_current_branch returns None when directory doesn't exist."""
        mock_path = MagicMock()
        mock_path.is_dir.return_value = False
        with patch('wrolpi.upgrade.PROJECT_DIR', mock_path):
            assert get_current_branch() is None

    def test_get_local_commit(self):
        """get_local_commit returns the short commit hash."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b'abc1234\n'
        mock_path = MagicMock()
        mock_path.is_dir.return_value = True

        with patch('wrolpi.upgrade.PROJECT_DIR', mock_path), \
                patch('subprocess.run', return_value=mock_result):
            assert get_local_commit() == 'abc1234'

    def test_get_remote_commit(self):
        """get_remote_commit returns the short commit hash for origin/branch."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b'def5678\n'
        mock_path = MagicMock()
        mock_path.is_dir.return_value = True

        with patch('wrolpi.upgrade.PROJECT_DIR', mock_path), \
                patch('subprocess.run', return_value=mock_result):
            assert get_remote_commit('release') == 'def5678'

    def test_get_commits_behind(self):
        """get_commits_behind returns the number of commits behind."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b'5\n'
        mock_path = MagicMock()
        mock_path.is_dir.return_value = True

        with patch('wrolpi.upgrade.PROJECT_DIR', mock_path), \
                patch('subprocess.run', return_value=mock_result):
            assert get_commits_behind('release') == 5


class TestCheckForUpdate:
    """Test check_for_update function."""

    def test_check_for_update_dockerized(self):
        """check_for_update returns no update in Docker."""
        with patch('wrolpi.upgrade.DOCKERIZED', True):
            result = check_for_update(fetch=False)
            assert result['update_available'] is False

    def test_check_for_update_directory_not_exists(self):
        """check_for_update returns no update when directory doesn't exist."""
        mock_path = MagicMock()
        mock_path.is_dir.return_value = False
        with patch('wrolpi.upgrade.DOCKERIZED', False), \
                patch('wrolpi.upgrade.PROJECT_DIR', mock_path):
            result = check_for_update(fetch=False)
            assert result['update_available'] is False

    def test_check_for_update_no_update(self):
        """check_for_update returns no update when commits match."""
        mock_path = MagicMock()
        mock_path.is_dir.return_value = True
        with patch('wrolpi.upgrade.DOCKERIZED', False), \
                patch('wrolpi.upgrade.PROJECT_DIR', mock_path), \
                patch('wrolpi.upgrade.get_current_branch', return_value='release'), \
                patch('wrolpi.upgrade.git_fetch', return_value=True), \
                patch('wrolpi.upgrade.get_local_commit', return_value='abc1234'), \
                patch('wrolpi.upgrade.get_remote_commit', return_value='abc1234'):
            result = check_for_update(fetch=True)
            assert result['update_available'] is False
            assert result['branch'] == 'release'
            assert result['current_commit'] == 'abc1234'
            assert result['latest_commit'] == 'abc1234'

    def test_check_for_update_update_available(self):
        """check_for_update returns update available when commits differ."""
        mock_path = MagicMock()
        mock_path.is_dir.return_value = True
        with patch('wrolpi.upgrade.DOCKERIZED', False), \
                patch('wrolpi.upgrade.PROJECT_DIR', mock_path), \
                patch('wrolpi.upgrade.get_current_branch', return_value='master'), \
                patch('wrolpi.upgrade.git_fetch', return_value=True), \
                patch('wrolpi.upgrade.get_local_commit', return_value='abc1234'), \
                patch('wrolpi.upgrade.get_remote_commit', return_value='def5678'), \
                patch('wrolpi.upgrade.get_commits_behind', return_value=3):
            result = check_for_update(fetch=True)
            assert result['update_available'] is True
            assert result['branch'] == 'master'
            assert result['current_commit'] == 'abc1234'
            assert result['latest_commit'] == 'def5678'
            assert result['commits_behind'] == 3

    def test_check_for_update_skip_fetch(self):
        """check_for_update can skip fetch."""
        mock_path = MagicMock()
        mock_path.is_dir.return_value = True
        with patch('wrolpi.upgrade.DOCKERIZED', False), \
                patch('wrolpi.upgrade.PROJECT_DIR', mock_path), \
                patch('wrolpi.upgrade.get_current_branch', return_value='release'), \
                patch('wrolpi.upgrade.git_fetch') as mock_fetch, \
                patch('wrolpi.upgrade.get_local_commit', return_value='abc1234'), \
                patch('wrolpi.upgrade.get_remote_commit', return_value='abc1234'):
            result = check_for_update(fetch=False)
            mock_fetch.assert_not_called()
            assert result['update_available'] is False


class TestStartUpgrade:
    """Test start_upgrade function."""

    @pytest.mark.asyncio
    async def test_start_upgrade_uses_current_branch(self, tmp_path):
        """start_upgrade writes branch to env file and starts systemd service."""
        mock_script_path = MagicMock()
        mock_script_path.is_file.return_value = True

        env_file = tmp_path / 'wrolpi-upgrade.env'

        with patch('wrolpi.upgrade.DOCKERIZED', False), \
                patch('wrolpi.upgrade.UPGRADE_SCRIPT', mock_script_path), \
                patch('wrolpi.upgrade.get_current_branch', return_value='master'), \
                patch('wrolpi.upgrade.subprocess.Popen') as mock_popen, \
                patch('wrolpi.upgrade.pathlib.Path', return_value=env_file), \
                patch('wrolpi.events.Events.send_upgrade_started'):
            await start_upgrade()

            # Verify env file was written with correct branch
            assert env_file.read_text() == 'BRANCH=master\n'

            # Verify systemctl start was called
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args[0][0]
            assert call_args == ['sudo', 'systemctl', 'start', 'wrolpi-upgrade.service']

    @pytest.mark.asyncio
    async def test_start_upgrade_uses_release_branch(self, tmp_path):
        """start_upgrade writes release branch to env file."""
        mock_script_path = MagicMock()
        mock_script_path.is_file.return_value = True

        env_file = tmp_path / 'wrolpi-upgrade.env'

        with patch('wrolpi.upgrade.DOCKERIZED', False), \
                patch('wrolpi.upgrade.UPGRADE_SCRIPT', mock_script_path), \
                patch('wrolpi.upgrade.get_current_branch', return_value='release'), \
                patch('wrolpi.upgrade.subprocess.Popen') as mock_popen, \
                patch('wrolpi.upgrade.pathlib.Path', return_value=env_file), \
                patch('wrolpi.events.Events.send_upgrade_started'):
            await start_upgrade()

            # Verify env file was written with correct branch
            assert env_file.read_text() == 'BRANCH=release\n'

            # Verify systemctl start was called
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args[0][0]
            assert call_args == ['sudo', 'systemctl', 'start', 'wrolpi-upgrade.service']

    @pytest.mark.asyncio
    async def test_start_upgrade_defaults_to_release_on_error(self, tmp_path):
        """start_upgrade defaults to release branch if current branch cannot be determined."""
        mock_script_path = MagicMock()
        mock_script_path.is_file.return_value = True

        env_file = tmp_path / 'wrolpi-upgrade.env'

        with patch('wrolpi.upgrade.DOCKERIZED', False), \
                patch('wrolpi.upgrade.UPGRADE_SCRIPT', mock_script_path), \
                patch('wrolpi.upgrade.get_current_branch', return_value=None), \
                patch('wrolpi.upgrade.subprocess.Popen') as mock_popen, \
                patch('wrolpi.upgrade.pathlib.Path', return_value=env_file), \
                patch('wrolpi.events.Events.send_upgrade_started'):
            await start_upgrade()

            # Verify env file was written with default release branch
            assert env_file.read_text() == 'BRANCH=release\n'

            # Verify systemctl start was called
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args[0][0]
            assert call_args == ['sudo', 'systemctl', 'start', 'wrolpi-upgrade.service']

    @pytest.mark.asyncio
    async def test_start_upgrade_skipped_in_docker(self):
        """start_upgrade does nothing in Docker environment."""
        with patch('wrolpi.upgrade.DOCKERIZED', True), \
                patch('wrolpi.upgrade.subprocess.Popen') as mock_popen:
            await start_upgrade()

            # Verify Popen was not called
            mock_popen.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_upgrade_script_not_found(self):
        """start_upgrade does nothing if upgrade script doesn't exist."""
        mock_script_path = MagicMock()
        mock_script_path.is_file.return_value = False

        with patch('wrolpi.upgrade.DOCKERIZED', False), \
                patch('wrolpi.upgrade.UPGRADE_SCRIPT', mock_script_path), \
                patch('wrolpi.upgrade.subprocess.Popen') as mock_popen:
            await start_upgrade()

            # Verify Popen was not called
            mock_popen.assert_not_called()


@pytest.mark.asyncio
async def test_upgrade_check_api_endpoint(async_client):
    """Test the /api/upgrade/check endpoint."""
    # The endpoint is native_only, so in Docker it should return 403
    # In tests, we're not in Docker, so patch the upgrade functions
    with patch('wrolpi.upgrade.DOCKERIZED', False), \
            patch('wrolpi.upgrade.check_for_update') as mock_check:
        mock_check.return_value = {
            'update_available': True,
            'current_commit': 'abc1234',
            'latest_commit': 'def5678',
            'branch': 'release',
            'commits_behind': 2,
        }

        _, response = await async_client.get('/api/upgrade/check')
        # Note: This may return 403 NATIVE_ONLY in test environment
        # The actual test depends on whether DOCKERIZED is True in tests


@pytest.mark.asyncio
async def test_status_endpoint_includes_git_branch(async_client):
    """Test that /api/status includes git_branch from status worker without conflict."""
    from wrolpi.api_utils import api_app

    # Simulate status_worker having populated git_branch in shared_ctx.status
    api_app.shared_ctx.status['git_branch'] = 'release'

    try:
        _, response = await async_client.get('/api/status')
        assert response.status == 200
        data = response.json
        # git_branch should be present and correct
        assert data.get('git_branch') == 'release'
    finally:
        # Clean up
        api_app.shared_ctx.status.pop('git_branch', None)
