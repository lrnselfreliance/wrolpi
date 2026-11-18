"""
Unit tests for controller.lib.rsyncd: the rsync daemon that serves the library to secondary WROLPis.
"""

import shutil
import socket
import subprocess
import time
from pathlib import Path
from unittest import mock

import pytest

from controller.lib import rsyncd
from controller.lib.docker_services import NON_VIEWABLE_CONTAINERS

REPOSITORY = Path(__file__).parent.parent.parent


class FakeNotFound(Exception):
    pass


def make_client(helper=None):
    api = mock.Mock()
    api.id, api.name, api.image.id = "api-id", "wrolpi-api-1", "sha256:image"
    api.attrs = {"Config": {"User": "1000:1000"}}
    client = mock.Mock()

    def get(name):
        if name == "wrolpi-api-1":
            return api
        if helper is not None:
            return helper
        raise FakeNotFound(name)

    client.containers.get.side_effect = get
    return client


def ensure(client):
    with mock.patch.object(rsyncd, "can_manage_containers", return_value=True), \
            mock.patch.object(rsyncd, "_get_client", return_value=client), \
            mock.patch.object(rsyncd, "NotFound", FakeNotFound):
        return rsyncd.ensure_rsync_daemon()


def current_source(client) -> str:
    """The label a helper made by this code from this api container carries."""
    ensure(client)
    return client.containers.run.call_args.kwargs["labels"][rsyncd.SOURCE_LABEL]


class TestConfig:

    def test_port(self):
        assert rsyncd.get_rsyncd_port() == 8873
        assert rsyncd.get_rsyncd_port("port = 9000\n[media]\n") == 9000
        with pytest.raises(RuntimeError):
            rsyncd.get_rsyncd_port("[media]\n")

    def test_unit_reads_the_same_config(self):
        """A Raspberry Pi, Debian and Docker all serve by one config file."""
        unit = (REPOSITORY / "etc/raspberrypios/wrolpi-rsyncd.service").read_text()
        assert "--config=/opt/wrolpi/controller/rsyncd.conf" in unit
        assert rsyncd.RSYNCD_CONFIG == REPOSITORY / "controller/rsyncd.conf"
        assert "User=wrolpi" in unit

    def test_units_installed_and_enabled(self):
        for script in ("repair.sh", "pi-gen/stage2/04-wrolpi/03-run-chroot.sh",
                       "debian-live-config/config/includes.chroot/usr/local/sbin/wrolpi-bootstrap.sh"):
            assert "wrolpi-rsyncd.service" in (REPOSITORY / script).read_text(), script
        assert "rsync" in (REPOSITORY / "docker/api/Dockerfile").read_text()


@pytest.mark.skipif(not shutil.which("rsync") or b"rsync  version 3" not in subprocess.run(
    ["rsync", "--version"], capture_output=True).stdout, reason="needs rsync 3")
def test_daemon_serves_the_library_read_only(tmp_path):
    """The daemon run with the real config (only its port and path changed) lists the library, never serves the
    database in use or the TLS keys, serves the snapshot, and refuses a write."""
    media = tmp_path / "media"
    for path in ("videos/a.mp4", "config/tags.yaml", "config/wrolpi.db", "config/wrolpi.db-wal",
                 "config/ssl/ca.key", "config/cookies.txt.enc", "config/.sync/config/wrolpi.db"):
        (media / path).parent.mkdir(parents=True, exist_ok=True)
        (media / path).write_text(path)
    # Links that anyone able to write to the library could make, to what the daemon leaves out.  Relative: rsync
    # already makes an absolute link point nowhere.
    (media / "videos/keys").symlink_to("../config/ssl")
    (media / "videos/key").symlink_to("../config/ssl/ca.key")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = rsyncd.read_rsyncd_config().replace("port = 8873", f"port = {port}\naddress = 127.0.0.1") \
        .replace("path = /media/wrolpi", f"path = {media}").replace("log file = /dev/stderr", "")
    assert str(media) in config and str(port) in config
    config_file = tmp_path / "rsyncd.conf"
    config_file.write_text(config)

    daemon = subprocess.Popen(["rsync", "--daemon", "--no-detach", f"--config={config_file}"])
    try:
        url = f"rsync://127.0.0.1:{port}/media/"
        for _ in range(50):
            listing = subprocess.run(["rsync", "-r", "--list-only", url], capture_output=True, text=True)
            if listing.returncode == 0:
                break
            time.sleep(0.1)
        assert listing.returncode == 0, listing.stderr
        listed = {line.split()[-1] for line in listing.stdout.splitlines() if line.startswith("-")}
        assert listed == {"videos/a.mp4", "config/tags.yaml", "config/.sync/config/wrolpi.db"}

        # Followed links are refused; without the option the links arrive as links, never as what they point at.
        for option in ("--copy-links", "--copy-unsafe-links", "--copy-dirlinks"):
            followed = subprocess.run(["rsync", "-r", option, url, str(tmp_path / "followed")],
                                      capture_output=True, text=True)
            assert followed.returncode != 0, option
            assert "refuse" in followed.stderr, followed.stderr
        leaked = [i for i in (tmp_path / "followed").rglob("*") if i.is_file() and "ssl/ca.key" in i.read_text()]
        assert not leaked, "a link let a client read the TLS key"
        copied = tmp_path / "copied"
        assert subprocess.run(["rsync", "-a", url, f"{copied}/"], capture_output=True).returncode == 0
        assert (copied / "videos/key").is_symlink() and (copied / "videos/keys").is_symlink()
        assert not (copied / "config/ssl").exists()

        (tmp_path / "new.txt").write_text("new")
        write = subprocess.run(["rsync", str(tmp_path / "new.txt"), url], capture_output=True, text=True)
        assert write.returncode != 0 and "read only" in write.stderr
        assert not (media / "new.txt").exists()
    finally:
        daemon.terminate()
        daemon.wait(timeout=10)


class TestEnsureRsyncDaemon:

    def test_not_in_docker(self):
        with mock.patch.object(rsyncd, "can_manage_containers", return_value=False):
            assert rsyncd.ensure_rsync_daemon()["success"] is False

    def test_creates_the_helper_from_the_api_container(self):
        client = make_client()
        assert ensure(client) == {"success": True, "action": "created"}
        args, kwargs = client.containers.run.call_args
        assert args[0] == "sha256:image", "the api container's own image"
        assert kwargs["entrypoint"] == "sh" and "rsync --daemon" in args[1][1], "not the image's API entrypoint"
        assert kwargs["volumes_from"] == ["wrolpi-api-1:ro"], "the api container's volumes, read-only"
        assert kwargs["user"] == "1000:1000"
        assert kwargs["ports"] == {"8873/tcp": 8873}
        assert kwargs["environment"]["RSYNCD_CONF"] == rsyncd.read_rsyncd_config()
        assert kwargs["name"] == "wrolpi-rsyncd-1" and kwargs["detach"] is True
        assert kwargs["restart_policy"] == {"Name": "unless-stopped"}

    def test_keeps_its_own_helper(self):
        helper = mock.Mock(status="running")
        helper.labels = {rsyncd.SOURCE_LABEL: current_source(make_client())}
        client = make_client(helper)
        assert ensure(client) == {"success": True, "action": "kept"}
        client.containers.run.assert_not_called()
        helper.start.assert_not_called()
        helper.remove.assert_not_called()

    def test_starts_a_stopped_helper(self):
        helper = mock.Mock(status="exited")
        helper.labels = {rsyncd.SOURCE_LABEL: current_source(make_client())}
        assert ensure(make_client(helper))["action"] == "kept"
        helper.start.assert_called_once()

    def test_replaces_a_helper_made_from_another_api_container(self):
        """A recreated api container may have other volumes; the helper must serve what the API has now."""
        helper = mock.Mock(status="running")
        helper.labels = {rsyncd.SOURCE_LABEL: "made from an older api container"}
        client = make_client(helper)
        assert ensure(client)["action"] == "created"
        helper.remove.assert_called_once_with(force=True)
        client.containers.run.assert_called_once()

    def test_never_raises(self):
        client = make_client()
        client.containers.run.side_effect = RuntimeError("no such image")
        result = ensure(client)
        assert result["success"] is False and "no such image" in result["error"]

    def test_not_given_a_view_button(self):
        assert "rsyncd" in NON_VIEWABLE_CONTAINERS
