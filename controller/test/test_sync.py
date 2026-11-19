"""
Unit tests for controller.lib.sync: a secondary WROLPi copying its primary with rsync.
"""

import datetime
import os
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
from collections import namedtuple
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from controller.lib import rsyncd, sync
from controller.main import app

PRIMARY = "https://primary.example:8443"
INFO = dict(role="primary", version="1.0", database_revision="abc", media_mounted=True, media_directory="/media/wrolpi")
RSYNC_3 = bool(shutil.which("rsync")) and b"rsync  version 3" in subprocess.run(
    ["rsync", "--version"], capture_output=True).stdout


@pytest.fixture
def media(tmp_path, monkeypatch) -> Path:
    """This machine's media directory: a mounted secondary of PRIMARY."""
    directory = tmp_path / "media"
    (directory / "config").mkdir(parents=True)
    (directory / "config/controller.yaml").write_text("{}")
    (directory / "config/sync.yaml").write_text(yaml.safe_dump(dict(role="secondary", primary_url=PRIMARY)))
    monkeypatch.setenv("MEDIA_DIRECTORY", str(directory))
    monkeypatch.setattr(sync, "_status", None)
    sync._cancel.clear()
    yield directory
    assert not sync._run_lock.locked(), "the test left a sync running"


def make_database(file: Path, value: str):
    file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(file) as connection:
        connection.execute("CREATE TABLE t (name TEXT)")
        connection.execute("INSERT INTO t VALUES (?)", (value,))
    connection.close()


def read_database(file: Path) -> str:
    connection = sqlite3.connect(f"file:{file}?mode=ro", uri=True)
    try:
        return connection.execute("SELECT name FROM t").fetchone()[0]
    finally:
        connection.close()


class FakeRunner:
    """Records what a sync does to the API, and plays rsync."""

    def __init__(self, media: Path, code: int = 0, on_files=None):
        self.media, self.code, self.on_files = media, code, on_files
        self.events = []

    def check(self):
        self.events.append("check")

    def stop_api(self):
        self.events.append("stop_api")

    def start_api(self):
        self.events.append("start_api")

    def stop_rsync(self):
        self.events.append("stop_rsync")

    def rsync(self, arguments, on_line):
        if arguments[-1].endswith("/"):
            self.files_command = arguments
            self.events.append("files")
            on_line("     1234567  42%   10.00MB/s    0:00:01")
            on_line("Number of regular files transferred: 7")
            if self.on_files:
                self.on_files()
            return self.code
        if arguments[-1].endswith("primary-wrolpi.yaml"):
            Path(arguments[-1]).write_text("videos_destination: videos\nplaylists_destination: lists\n")
            return 0
        self.events.append("database")
        make_database(Path(arguments[-1]), "from the primary")
        return 0


@pytest.fixture
def primary_api(monkeypatch):
    """The primary's and this machine's APIs answer; both run the same WROLPi."""
    monkeypatch.setattr(sync, "get_primary_info", lambda url: dict(INFO))
    monkeypatch.setattr(sync, "get_local_info", lambda: dict(INFO, role="secondary"))
    monkeypatch.setattr(sync, "request_snapshot", lambda url: dict(size=1000, written=True))
    monkeypatch.setattr(sync, "wait_for_api", lambda: True)


class TestCommand:

    def test_copies_everything_but_what_is_local(self, media):
        command = sync.build_files_command(PRIMARY, media, media / ".sync-trash/2026-11-18", ["old [stuff]", "a/b/"],
                                           ["my playlists", "lists", "my playlists"])
        assert command[-2:] == ["rsync://primary.example:8873/media/", f"{media}/"]
        assert "--delete" in command and "--backup" in command
        assert f"--backup-dir={media}/.sync-trash/2026-11-18" in command
        for excluded in ("/tags", "/my playlists", "/lists", "/config/wrolpi.yaml", "/config/sync.yaml", "/config/ssl",
                         "/config/wrolpi.db", "/config/wrolpi.db-wal", "/config/.sync", "/.sync-trash",
                         "/config/sync_state.yaml", "/config/.wrol_mode", "/old \\[stuff]", "/a/b"):
            assert f"--exclude={excluded}" in command, excluded
        # Unfinished files are only hidden from the primary's side, so the secondary's stale ones are deleted.
        for hidden in ("*.part", ".partial", "*.db-wal", "*.db-shm"):
            assert f"--filter=H {hidden}" in command and f"--exclude={hidden}" not in command, hidden
        # A pattern ending in a slash matches only a directory; a file or link of that name would get through.
        assert not [i for i in command if i.startswith("--exclude=") and i.endswith("/")]
        assert command.count("--exclude=/my playlists") == 1
        # A primary that stops answering ends the run; rsync alone would wait forever with the API stopped.
        assert "--contimeout=30" in command and "--timeout=300" in command
        # Only links that stay inside the library, and no device files.
        assert "--safe-links" in command and "--devices" not in command and "--specials" not in command
        # An ignored directory is still part of the library: nothing leaves out the map or the repos.
        assert not [i for i in command if "map" in i or "repos" in i]
        # Owner and group are this machine's.
        assert "--archive" not in command and "--owner" not in command

    def test_database_is_never_judged_the_same_by_size_and_time(self, media):
        command = sync.build_database_command(PRIMARY, media)
        assert "--ignore-times" in command and f"--copy-dest={media}/config" in command
        assert "--contimeout=30" in command and "--timeout=300" in command
        assert command[-2:] == ["rsync://primary.example:8873/media/config/.sync/config/wrolpi.db",
                                f"{media}/config/.sync/incoming/wrolpi.db"]

    def test_never_deletes_without_a_trash(self, media):
        """Without a trash nothing of the library is deleted; only the secondary's stale unfinished files are."""
        command = sync.build_files_command(PRIMARY, media, None)
        assert "--backup" not in command
        protect = command.index("--filter=P *")
        for pattern in sync.UNFINISHED_PATTERNS:
            # rsync uses the first rule that matches: the risk rules must come before the protect rule.
            assert command.index(f"--filter=R {pattern}") < protect, pattern
            assert command.index(f"--filter=R {pattern}/**") < protect, pattern

    @pytest.mark.parametrize("url, expected", [
        ("https://10.0.0.5", "rsync://10.0.0.5:8873/media/"),
        ("https://wrolpi.local:8443", "rsync://wrolpi.local:8873/media/"),
        ("https://[fd00::5]:8443", "rsync://[fd00::5]:8873/media/"),
    ])
    def test_rsync_url(self, url, expected):
        assert sync.rsync_url(url) == expected
        assert sync.rsync_url(url, "config/wrolpi.yaml") == expected + "config/wrolpi.yaml"

    def test_rsync_url_invalid(self):
        with pytest.raises(sync.SyncError):
            sync.rsync_url("not an address")

    @pytest.mark.parametrize("line, expected", [
        ("    32768000  12%   31.25MB/s    0:00:07 (xfr#3, to-chk=10/20)",
         dict(bytes_transferred=32768000, percent=12)),
        ("Number of regular files transferred: 1,234", dict(files_transferred=1234)),
        ("Number of deleted files: 3 (reg: 2, dir: 1)", dict(files_deleted=3)),
        ("sending incremental file list", {}),
    ])
    def test_parse_rsync_line(self, line, expected):
        assert sync.parse_rsync_line(line) == expected

    @pytest.mark.parametrize("config, expected", [
        ({}, 30), (dict(delete_after_days=7), 7), (dict(delete_after_days=0), 0), (dict(delete_after_days=None), None),
    ])
    def test_delete_after_days(self, config, expected):
        assert sync.get_delete_after_days(config) == expected


class TestRootInAnotherUsersDirectory:
    """The Controller runs as root; the media directory belongs to the wrolpi user, who must not be able to point
    root somewhere else with a symbolic link."""

    def test_state_is_not_written_through_a_link(self, media, tmp_path):
        target = tmp_path / "somewhere else.txt"
        target.write_text("untouched")
        (media / "config/sync_state.yaml").symlink_to(target)
        sync.update_status(save=True, last_error="x")
        assert target.read_text() == "untouched"

    def test_write_file_replaces_never_follows(self, media, tmp_path):
        target = tmp_path / "somewhere else.txt"
        target.write_text("untouched")
        (media / "config/.sync").symlink_to(tmp_path)
        with pytest.raises(sync.SyncError, match="symbolic link"):
            sync.write_file(media / sync.PRIMARY_INFO, "x")
        with pytest.raises(sync.SyncError, match="symbolic link"):
            sync.make_directory(media / sync.SYNC_DIRECTORY / "incoming")
        assert not (tmp_path / "incoming").exists() and not (tmp_path / "primary-info.yaml").exists()

    def test_files_belong_to_the_library_owner(self, media, monkeypatch):
        chowned = []
        monkeypatch.setattr(sync.os, "fchown", lambda fd, uid, gid: chowned.append((uid, gid)))
        sync.make_directory(media / sync.SYNC_DIRECTORY)
        sync.write_file(media / sync.PRIMARY_INFO, "media_directory: /media/wrolpi\n")
        owner = media.stat()
        assert chowned == [(owner.st_uid, owner.st_gid)]
        assert (media / sync.PRIMARY_INFO).read_text() == "media_directory: /media/wrolpi\n"

    def test_directories_belong_to_the_library_owner(self, media, monkeypatch):
        """rsync does not run as root, and must write into what the Controller made."""
        chowned = []
        monkeypatch.setattr(sync.os, "chown", lambda path, uid, gid, follow_symlinks=True: chowned.append(
            (Path(path).relative_to(media).as_posix(), uid, gid)))
        owner = media.stat()
        sync.make_directory(media / sync.SYNC_DIRECTORY / "incoming")
        assert sorted(chowned) == [("config/.sync", owner.st_uid, owner.st_gid),
                                   ("config/.sync/incoming", owner.st_uid, owner.st_gid)]
        chowned.clear()
        sync.make_directory(media / sync.SYNC_DIRECTORY / "incoming")
        assert chowned == [], "only what it made"

    def test_trash_that_is_a_link_is_not_purged(self, media, tmp_path):
        elsewhere = tmp_path / "elsewhere"
        (elsewhere / "2020-01-01").mkdir(parents=True)
        (media / ".sync-trash").symlink_to(elsewhere)
        assert sync.purge_trash(media, 30, datetime.date(2026, 11, 18), min_free_bytes=0) == []
        assert (elsewhere / "2020-01-01").is_dir()

        (media / ".sync-trash").unlink()
        (media / ".sync-trash").mkdir()
        (media / ".sync-trash/2020-01-02").symlink_to(elsewhere / "2020-01-01")
        assert sync.purge_trash(media, 30, datetime.date(2026, 11, 18), min_free_bytes=0) == []
        assert (elsewhere / "2020-01-01").is_dir()

    def test_database_that_is_a_link_is_not_replaced(self, media, tmp_path):
        make_database(tmp_path / "elsewhere.db", "somewhere else")
        (media / "config/wrolpi.db").symlink_to(tmp_path / "elsewhere.db")
        make_database(media / sync.INCOMING_DATABASE, "from the primary")
        with pytest.raises(sync.SyncError, match="symbolic link"):
            sync.replace_database(media)
        assert read_database(tmp_path / "elsewhere.db") == "somewhere else"


class TestChecks:

    def test_skip_reason(self, media):
        assert sync.skip_reason() is None
        assert sync.skip_reason(dict(role="primary", primary_url=PRIMARY)) == "This WROLPi is not a secondary"
        assert sync.skip_reason(dict(role="secondary")) == "No primary is configured"
        (media / "config/.wrol_mode").touch()
        assert sync.skip_reason() == "WROL Mode is enabled"
        (media / "config/.wrol_mode").unlink()
        (media / "config/controller.yaml").unlink()
        assert sync.skip_reason() == "The media directory is not mounted"

    @pytest.mark.parametrize("change, message", [
        (dict(role="secondary"), "not a primary"),
        (dict(media_mounted=False), "not mounted"),
        (dict(version="2.0"), "WROLPi version"),
        (dict(database_revision="def"), "database migration"),
        (dict(database_revision=None), "database migration"),
        # The database names every file by its full path.
        (dict(media_directory="/data/library"), "media directory"),
        (dict(media_directory=None), "media directory"),
    ])
    def test_check_primary_refuses(self, change, message):
        with pytest.raises(sync.SyncError, match=message):
            sync.check_primary(dict(INFO, **change), dict(INFO))

    def test_check_primary(self):
        sync.check_primary(dict(INFO), dict(INFO, role="secondary"))


class TestPurge:

    def test_by_the_name_of_the_folder(self, media):
        """A folder is as old as its name says; files keep the modification times they had in the library."""
        today = datetime.date(2026, 11, 18)
        trash = media / ".sync-trash"
        for name in ("2026-10-18", "2026-10-19", "2026-10-20", "2026-11-18", "not a date"):
            (trash / name).mkdir(parents=True)
            (trash / name / "file.txt").write_text("deleted on the primary")
        assert sync.purge_trash(media, 30, today, min_free_bytes=0) == ["2026-10-18", "2026-10-19"]
        assert sorted(i.name for i in trash.iterdir()) == ["2026-10-20", "2026-11-18", "not a date"]

    def test_never(self, media):
        (media / ".sync-trash/2020-01-01").mkdir(parents=True)
        assert sync.purge_trash(media, None, datetime.date(2026, 11, 18), min_free_bytes=0) == []

    def test_oldest_first_when_the_drive_is_nearly_full(self, media, monkeypatch):
        """A full drive is worse than a shorter wait: the oldest trash goes until there is room again."""
        trash = media / ".sync-trash"
        for name in ("2026-11-16", "2026-11-17", "2026-11-18"):
            (trash / name).mkdir(parents=True)
        usage = namedtuple("usage", "total used free")
        monkeypatch.setattr(sync.shutil, "disk_usage",
                            lambda _: usage(100, 0, 5 if (trash / "2026-11-16").exists() else 50))
        assert sync.purge_trash(media, 30, datetime.date(2026, 11, 18), min_free_bytes=10) == ["2026-11-16"]


class TestReplaceDatabase:

    def test_replaces_and_removes_the_old_log(self, media):
        """A log left beside the old database (by an API that was killed) would be applied to the new one."""
        database = media / "config/wrolpi.db"
        make_database(database, "this secondary's")
        live = sqlite3.connect(database)
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("UPDATE t SET name = 'written to the log'")
        live.commit()
        log = database.with_name("wrolpi.db-wal")
        left_behind = log.read_bytes()
        assert left_behind
        live.close()
        log.write_bytes(left_behind)
        incoming = media / sync.INCOMING_DATABASE
        make_database(incoming, "from the primary")
        with sqlite3.connect(incoming) as connection:
            # The snapshot of a database in WAL mode is in WAL mode too.
            connection.execute("PRAGMA journal_mode=WAL")
        connection.close()

        sync.replace_database(media)

        assert not database.with_name("wrolpi.db-wal").exists() and not database.with_name("wrolpi.db-shm").exists()
        # Nothing is left where the snapshot was; a log there would be applied to the next snapshot.
        assert not list(incoming.parent.iterdir()), list(incoming.parent.iterdir())
        assert read_database(database) == "from the primary"

    def test_refuses_what_is_not_a_database(self, media):
        make_database(media / "config/wrolpi.db", "this secondary's")
        incoming = media / sync.INCOMING_DATABASE
        incoming.parent.mkdir(parents=True)
        incoming.write_bytes(b"")
        with pytest.raises(sync.SyncError, match="not a database"):
            sync.replace_database(media)
        assert read_database(media / "config/wrolpi.db") == "this secondary's"


class TestRunSync:

    def test_order_and_outcome(self, media, primary_api):
        """The API is down only while the library is replaced, and what the run did survives a restart."""
        make_database(media / "config/wrolpi.db", "this secondary's")
        runner = FakeRunner(media)

        status = sync.run_sync(runner)

        assert runner.events == ["check", "stop_api", "files", "database", "start_api"]
        assert status["state"] == "idle" and status["last_error"] is None and status["last_success_at"]
        assert status["files_transferred"] == 7 and status["primary_version"] == "1.0"
        assert read_database(media / "config/wrolpi.db") == "from the primary"
        assert yaml.safe_load((media / sync.PRIMARY_INFO).read_text())["media_directory"] == "/media/wrolpi"
        assert (media / sync.PRIMARY_WROLPI_CONFIG).is_file()
        # A restarted Controller reads the state file.
        sync._status = None
        assert sync.get_status()["last_success_at"] == status["last_success_at"]

    def test_leaves_out_the_playlists_of_both_machines(self, media, primary_api):
        """The primary names its playlists directory in its own wrolpi.yaml, which is fetched before the copy: its
        hard links would arrive as full copies.  This machine's own playlists directory must not be deleted."""
        (media / "config/wrolpi.yaml").write_text("playlists_destination: mine\n")
        runner = FakeRunner(media)
        sync.run_sync(runner)
        assert "--exclude=/lists" in runner.files_command and "--exclude=/mine" in runner.files_command

    def test_trash_is_purged_even_when_the_copy_fails(self, media, primary_api):
        """A full drive fails every copy, and the trash is what fills it: it must be emptied before the copy."""
        (media / ".sync-trash/2020-01-01").mkdir(parents=True)
        status = sync.run_sync(FakeRunner(media, code=12))
        assert status["state"] == "error"
        assert not (media / ".sync-trash/2020-01-01").exists()

    @pytest.mark.parametrize("config", [
        dict(delete_after_days="soon"), dict(primary_url=["not", "text"]), dict(sync_excluded_directories=5),
    ])
    def test_a_bad_setting_ends_the_run_and_frees_it(self, media, primary_api, config):
        """sync.yaml can be edited by hand.  A value that cannot be used must not leave "A sync is already running"
        behind until the Controller restarts."""
        (media / "config/sync.yaml").write_text(yaml.safe_dump(dict(dict(role="secondary", primary_url=PRIMARY),
                                                                    **config)))
        runner = FakeRunner(media)
        status = sync.run_sync(runner)
        assert status["state"] == "error" and status["last_error"]
        assert not sync._run_lock.locked()
        assert runner.events.count("stop_api") == runner.events.count("start_api")
        assert sync.skip_reason(dict(role="secondary", primary_url=PRIMARY)) is None

    def test_a_refused_primary_changes_nothing(self, media, primary_api, monkeypatch):
        monkeypatch.setattr(sync, "get_primary_info", lambda url: dict(INFO, version="2.0"))
        runner = FakeRunner(media)
        status = sync.run_sync(runner)
        assert status["state"] == "error" and "upgrade both" in status["last_error"]
        assert runner.events == ["check"], "the API was never stopped"

    def test_failed_files_leave_the_database_and_start_the_api(self, media, primary_api):
        make_database(media / "config/wrolpi.db", "this secondary's")
        runner = FakeRunner(media, code=12)
        status = sync.run_sync(runner)
        assert status["state"] == "error" and "exit code 12" in status["last_error"]
        assert runner.events == ["check", "stop_api", "files", "start_api"]
        assert read_database(media / "config/wrolpi.db") == "this secondary's"
        assert status["last_success_at"] is None

    def test_files_that_vanished_are_only_a_warning(self, media, primary_api):
        """The primary is in use while it is copied."""
        status = sync.run_sync(FakeRunner(media, code=sync.RSYNC_VANISHED))
        assert status["state"] == "idle" and status["last_success_at"] and status["warnings"]

    def test_cancelled(self, media, primary_api):
        make_database(media / "config/wrolpi.db", "this secondary's")
        runner = FakeRunner(media, on_files=sync.request_cancel)
        status = sync.run_sync(runner)
        assert status["state"] == "idle" and status["last_error"] == "The sync was cancelled"
        assert runner.events[-1] == "start_api" and "database" not in runner.events
        assert read_database(media / "config/wrolpi.db") == "this secondary's"

    def test_wrol_mode_stops_it(self, media, primary_api):
        runner = FakeRunner(media, on_files=lambda: (media / "config/.wrol_mode").touch())
        status = sync.run_sync(runner)
        assert status["last_error"] == "WROL Mode was enabled" and runner.events[-1] == "start_api"

    def test_not_a_secondary(self, media, primary_api):
        (media / "config/sync.yaml").write_text("role: primary\n")
        runner = FakeRunner(media)
        assert sync.run_sync(runner)["last_error"] == "This WROLPi is not a secondary"
        assert runner.events == []

    def test_interrupted_sync_is_recovered(self, media):
        """A Controller that stopped during a sync left the API stopped."""
        sync.update_status(save=True, state="running", phase="files")
        sync._status = None
        runner = FakeRunner(media)
        sync.recover_interrupted_sync(runner)
        # In Docker rsync is its own container and is still replacing files: it is stopped before the API starts.
        assert runner.events == ["stop_rsync", "start_api"]
        assert sync.get_status()["state"] == "error" and sync.get_status()["last_error"] == "The sync was interrupted"

        runner = FakeRunner(media)
        sync.recover_interrupted_sync(runner)
        assert runner.events == [], "nothing to recover the second time"


class TestApi:

    def test_status_run_cancel(self, media, monkeypatch):
        client = TestClient(app)
        assert client.get("/api/sync/status").json()["state"] == "idle"

        started = threading.Event()
        monkeypatch.setattr(sync, "run_sync", started.set)
        assert client.post("/api/sync/run").status_code == 202
        assert started.wait(5)
        assert client.post("/api/sync/cancel").status_code == 202

        (media / "config/sync.yaml").write_text("role: primary\n")
        response = client.post("/api/sync/run")
        assert response.status_code == 409 and response.json()["detail"] == "This WROLPi is not a secondary"


class LocalRunner(sync.SystemdRunner):
    """Real rsync, as whoever runs the tests; the API is only recorded."""

    def __init__(self):
        self.events = []

    def stop_api(self):
        self.events.append("stop_api")

    def start_api(self):
        self.events.append("start_api")

    def rsync(self, arguments, on_line):
        process = subprocess.Popen(["rsync", *arguments], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return sync._follow(process.stdout.read1, on_line, process.terminate, process.wait)


def write(root: Path, files: dict):
    for path, content in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(content)


@pytest.mark.skipif(not RSYNC_3, reason="needs rsync 3")
def test_sync_with_a_real_daemon(media, tmp_path, primary_api, monkeypatch):
    """A whole sync against a real rsync daemon run with the real config: the secondary becomes a copy of its
    primary, ignored directories included; what the primary deleted or changed waits in the trash; what belongs to
    this machine is left alone; and a second sync finds nothing to do."""
    primary = tmp_path / "primary"
    write(primary, {
        "videos/a.mp4": "a video", "videos/changed.txt": "the primary's newer version",
        # Ignored on the primary, so in no FileGroup: the old sync never copied these.
        "map/region.pmtiles": "a map", "repos/tool/README.md": "a repo",
        "map/.partial/unfinished.pmtiles": "half a map", "map/region.search.db-wal": "in use",
        "excluded/big.bin": "not wanted here",
        "tags/one/a.mp4": "a hard link on the primary", "playlists/Watch/0001_a.mp4": "a hard link on the primary",
        "config/tags.yaml": "the primary's tags", "config/wrolpi.yaml": "videos_destination: videos\n",
        "config/sync.yaml": "role: primary\n", "config/controller.yaml": "the primary's",
        "config/ssl/ca.key": "the primary's key", "config/wrolpi.db": "the primary's database, in use",
    })
    make_database(primary / sync.SNAPSHOT_PATH, "from the primary")
    # A link inside the library is part of it; one that points outside would point at this machine's files.
    (primary / "videos/inside").symlink_to("a.mp4")
    (primary / "videos/outside").symlink_to("/etc/hostname")
    (primary / "videos/climbs out").symlink_to("../../outside.txt")
    # Where this machine has a directory of its own, the primary has a file of that name.
    (primary / "config/backup").write_text("not a directory on the primary")
    write(media, {"config/backup/tags-20261118.yaml": "this machine's config backup"})
    # The secondary's own: a log beside a search database the primary replaced, and an unfinished download.
    write(media, {"map/region.search.db-wal": "this machine's stale log", "map/.partial/old.pmtiles": "stale"})
    write(media, {
        "videos/changed.txt": "older", "videos/deleted on the primary.txt": "gone there",
        "tags/mine/x.txt": "this machine's links", "config/wrolpi.yaml": "hotspot_ssid: mine\n",
        "config/ssl/ca.key": "this machine's key",
    })
    (media / "config/sync.yaml").write_text(yaml.safe_dump(dict(
        role="secondary", primary_url="https://127.0.0.1:8443", sync_excluded_directories=["excluded"])))
    make_database(media / "config/wrolpi.db", "this secondary's")
    # The same size, written in the same second: the two databases look the same to a quick comparison.
    snapshot_stat = (primary / sync.SNAPSHOT_PATH).stat()
    assert (media / "config/wrolpi.db").stat().st_size == snapshot_stat.st_size
    os.utime(media / "config/wrolpi.db", ns=(snapshot_stat.st_atime_ns, snapshot_stat.st_mtime_ns))

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = rsyncd.read_rsyncd_config().replace("port = 8873", f"port = {port}\naddress = 127.0.0.1") \
        .replace("path = /media/wrolpi", f"path = {primary}").replace("log file = /dev/stderr", "")
    (tmp_path / "rsyncd.conf").write_text(config)
    monkeypatch.setattr(sync, "get_rsyncd_port", lambda: port)
    daemon = subprocess.Popen(["rsync", "--daemon", "--no-detach", f"--config={tmp_path / 'rsyncd.conf'}"])
    try:
        for _ in range(50):
            if subprocess.run(["rsync", f"rsync://127.0.0.1:{port}/"], capture_output=True).returncode == 0:
                break
            time.sleep(0.1)
        runner = LocalRunner()

        status = sync.run_sync(runner)

        assert status["state"] == "idle" and status["last_error"] is None, status
        assert runner.events == ["stop_api", "start_api"]
        for path in ("videos/a.mp4", "map/region.pmtiles", "repos/tool/README.md", "config/tags.yaml"):
            assert (media / path).read_text() == (primary / path).read_text(), path
        assert (media / "videos/changed.txt").read_text() == "the primary's newer version"
        assert (media / "videos/a.mp4").stat().st_mtime == (primary / "videos/a.mp4").stat().st_mtime
        # Deleted and replaced files wait in today's trash.
        trash = media / ".sync-trash" / datetime.date.today().isoformat()
        assert (trash / "videos/deleted on the primary.txt").read_text() == "gone there"
        assert (trash / "videos/changed.txt").read_text() == "older"
        assert not (media / "videos/deleted on the primary.txt").exists()
        # This machine's own, and what WROLPi rebuilds, are neither copied nor deleted.
        assert (media / "config/wrolpi.yaml").read_text() == "hotspot_ssid: mine\n"
        assert yaml.safe_load((media / "config/sync.yaml").read_text())["role"] == "secondary"
        assert (media / "config/ssl/ca.key").read_text() == "this machine's key"
        assert (media / "config/controller.yaml").read_text() == "{}"
        assert (media / "tags/mine/x.txt").exists() and not (media / "tags/one").exists()
        assert not (media / "playlists").exists()
        assert (media / "config/backup/tags-20261118.yaml").read_text() == "this machine's config backup"
        assert (media / "videos/inside").is_symlink() and (media / "videos/inside").read_text() == "a video"
        assert not (media / "videos/outside").is_symlink() and not (media / "videos/climbs out").is_symlink()
        # Unfinished files and the excluded folder stay on the primary; the secondary's own stale ones are gone
        # (to the trash, like any deleted file).
        assert not (media / "map/.partial").exists() and not (media / "map/region.search.db-wal").exists()
        assert (media / ".sync-trash" / datetime.date.today().isoformat() / "map/region.search.db-wal").read_text() \
            == "this machine's stale log"
        assert not (media / "excluded").exists()
        # The database is the primary's snapshot, never its database in use; the library settings come along.
        assert read_database(media / "config/wrolpi.db") == "from the primary"
        assert (media / sync.PRIMARY_WROLPI_CONFIG).read_text() == "videos_destination: videos\n"
        assert not (media / sync.SNAPSHOT_PATH).exists()
        assert status["files_transferred"] >= 4 and status["files_deleted"] >= 1 and status["trash_bytes"] > 0

        # Nothing changed: nothing is copied, and nothing more goes to the trash.
        before = sorted(i for i in trash.rglob("*"))
        status = sync.run_sync(LocalRunner())
        assert status["state"] == "idle" and status["files_transferred"] == 0 and status["files_deleted"] == 0
        assert sorted(i for i in trash.rglob("*")) == before
    finally:
        daemon.terminate()
        daemon.wait(timeout=10)


class TestDockerRunner:

    def make(self, monkeypatch, media, exit_code):
        from unittest import mock
        api = mock.Mock()
        seen = []

        def exec_run(command):
            seen.append(Path(command[-1]).exists())
            return mock.Mock(exit_code=exit_code)

        api.exec_run.side_effect = exec_run
        client = mock.Mock()
        client.containers.get.return_value = api
        monkeypatch.setattr(sync, "can_manage_containers", lambda: True)
        monkeypatch.setattr(sync, "_get_client", lambda: client)
        return sync.DockerRunner(), seen

    def test_refuses_when_the_api_container_has_another_media_directory(self, media, monkeypatch):
        """The Controller replaces the database in its own media directory; rsync writes to the api container's.
        A probe file the api container cannot see means they are two directories."""
        runner, seen = self.make(monkeypatch, media, exit_code=1)
        with pytest.raises(sync.SyncError, match="different media directories"):
            runner.check()
        assert seen == [True], "the probe existed while the api container was asked"
        assert not list((media / sync.SYNC_DIRECTORY).glob(".probe-*")), "and is removed"

    def test_stop_rsync_removes_the_helper(self, media, monkeypatch):
        from unittest import mock
        helper = mock.Mock()
        client = mock.Mock()
        client.containers.get.return_value = helper
        monkeypatch.setattr(sync, "_get_client", lambda: client)
        sync.DockerRunner().stop_rsync()
        client.containers.get.assert_called_once_with("wrolpi-sync-1")
        helper.remove.assert_called_once_with(force=True)

        client.containers.get.side_effect = RuntimeError("no such container")
        sync.DockerRunner().stop_rsync()

    def test_accepts_the_same_media_directory(self, media, monkeypatch):
        runner, _ = self.make(monkeypatch, media, exit_code=0)
        runner.check()
        assert not list((media / sync.SYNC_DIRECTORY).glob(".probe-*"))


@pytest.mark.skipif(not RSYNC_3, reason="needs rsync 3")
def test_a_primary_that_stops_answering_ends_rsync(media, monkeypatch):
    """A primary that accepts the connection and then says nothing (it lost power mid-copy, as far as TCP can tell):
    rsync gives up, so the run ends and the API is started again."""
    monkeypatch.setattr(sync, "RSYNC_IO_TIMEOUT_SECONDS", 2)
    monkeypatch.setattr(sync, "RSYNC_CONNECT_TIMEOUT_SECONDS", 2)
    with socket.socket() as silent:
        silent.bind(("127.0.0.1", 0))
        silent.listen()
        monkeypatch.setattr(sync, "get_rsyncd_port", lambda: silent.getsockname()[1])
        # Without its timeouts rsync never returns; stop it, so that is a failure here and not a test that hangs.
        gave_up = threading.Timer(30, sync._cancel.set)
        gave_up.start()
        try:
            code = LocalRunner().rsync(sync.build_files_command("https://127.0.0.1", media, None), lambda _: None)
        except sync.SyncCancelled:
            pytest.fail("rsync waited on a silent primary until it was stopped")
        finally:
            gave_up.cancel()
            sync._cancel.clear()
    assert code != 0


@pytest.mark.skipif(not RSYNC_3, reason="needs rsync 3")
def test_never_delete_still_removes_stale_logs(tmp_path):
    """With deletes turned off, a secondary keeps every file its primary no longer has, but not its own write-ahead
    log beside a database the primary replaced, which SQLite would apply to the new database."""
    primary, secondary = tmp_path / "primary", tmp_path / "secondary"
    make_database(primary / "map/region.search.db", "the primary's new index")
    write(secondary, {"map/region.search.db": "old", "map/region.search.db-wal": "this machine's stale log",
                      "map/.partial/old.pmtiles": "stale", "videos/deleted on the primary.mp4": "kept",
                      "kept folder/a.txt": "kept"})
    command = sync.build_files_command(PRIMARY, secondary, None)
    # From a local folder rather than a daemon, which takes no connection timeout.
    command = [i for i in command if not i.startswith("--contimeout")]
    command[-2] = f"{primary}/"
    result = subprocess.run(["rsync", *command], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr

    assert not (secondary / "map/region.search.db-wal").exists()
    assert not (secondary / "map/.partial/old.pmtiles").exists()
    assert (secondary / "videos/deleted on the primary.mp4").read_text() == "kept"
    assert (secondary / "kept folder/a.txt").read_text() == "kept"
    assert read_database(secondary / "map/region.search.db") == "the primary's new index"
    assert not (secondary / ".sync-trash").exists()
