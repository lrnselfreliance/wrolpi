"""
A secondary WROLPi copies its primary: the whole media directory, and the database.

The Controller runs it, because the secondary's API is stopped while its library is replaced:

1. Checks: this is a secondary, WROL Mode is off, the primary answers, runs the same WROLPi and database migration,
   and has its media directory mounted.  A failure here changes nothing.
2. The primary makes a snapshot of its database (see wrolpi.sync.snapshot).
3. The API is stopped.
4. rsync copies every file from the primary's daemon (controller/rsyncd.conf), ignored directories included.  Files
   the primary no longer has, and the old versions of files it changed, are moved to a dated folder in
   `.sync-trash` rather than deleted.
5. The database snapshot is copied beside the database, then takes its place.  Last, so that a run which stops
   earlier leaves a database that works.
6. The API is started.
7. Trash folders older than the delete delay are removed.

The settings are the API's `sync.yaml`; this module only reads them.  What a run did is kept in `sync_state.yaml`.
"""

import contextlib
import datetime
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
import zoneinfo
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import asyncio

import httpx
import yaml

from controller.lib.config import get_media_directory, is_docker_mode
from controller.lib.docker_services import _get_client, _get_container_name, can_manage_containers, \
    start_container, stop_container
from controller.lib.rsyncd import get_rsyncd_port
from controller.lib.systemd import start_service, stop_service
from controller.lib.wrol_mode import is_wrol_mode

logger = logging.getLogger(__name__)

TRASH_DIRECTORY = ".sync-trash"
PARTIAL_DIRECTORY = ".rsync-partial"
# Where the primary keeps its database snapshot, and where this secondary keeps what it fetched from its primary.
SYNC_DIRECTORY = "config/.sync"
SNAPSHOT_PATH = f"{SYNC_DIRECTORY}/config/wrolpi.db"
INCOMING_DATABASE = f"{SYNC_DIRECTORY}/incoming/wrolpi.db"
# The primary's wrolpi.yaml and /api/sync/info, from which the API takes the library settings when it starts.
PRIMARY_WROLPI_CONFIG = f"{SYNC_DIRECTORY}/primary-wrolpi.yaml"
PRIMARY_INFO = f"{SYNC_DIRECTORY}/primary-info.yaml"
STATE_FILE = "config/sync_state.yaml"
DEFAULT_DELETE_AFTER_DAYS = 30
# Never fill the secondary's drive; leave this much free.
MIN_FREE_BYTES = 1024 ** 3
# Within the daily sync window, a sync starts this long after the last one finished.
SYNC_REPEAT_SECONDS = 15 * 60
# How often the schedule is looked at.
SCHEDULE_INTERVAL_SECONDS = 60
SNAPSHOT_TIMEOUT_SECONDS = 60 * 60
API_START_TIMEOUT_SECONDS = 10 * 60
# A sync runs unattended with the API stopped: a primary that loses power or its link must end the run, not hold it.
# rsync's own default is to wait forever.
RSYNC_CONNECT_TIMEOUT_SECONDS = 30
RSYNC_IO_TIMEOUT_SECONDS = 300
# rsync: 23 = some files could not be transferred, 24 = some files vanished while copying (the primary is in use).
RSYNC_PARTIAL, RSYNC_VANISHED = 23, 24

# Never copied from the primary: what belongs to this machine, and what WROLPi rebuilds.  No trailing slash: a
# pattern that ends in one matches only a directory, and a file or link of that name on the primary would then
# replace this machine's directory.
LOCAL_PATHS = (
    # Hard links, rebuilt from the database when the API starts.
    "/tags",
    # This machine's settings and state.
    "/config/wrolpi.yaml", "/config/sync.yaml", "/config/controller.yaml", "/config/fstab.yaml",
    "/config/.fstab-migrated", "/config/smb.conf", f"/{STATE_FILE}", "/config/.wrol_mode", "/config/ssl",
    "/config/cookies.txt", "/config/cookies.txt.enc", "/config/backup",
    # The database arrives as a snapshot, in its own step.
    "/config/wrolpi.db", "/config/wrolpi.db-wal", "/config/wrolpi.db-shm", "/config/wrolpi.db.lock",
    f"/{SYNC_DIRECTORY}",
    f"/{TRASH_DIRECTORY}", "/lost+found",
)
# Anywhere in the library: files still being written on the primary, which are not copied.  Hidden from the
# primary's side only (rsync's "hide"), not excluded: the secondary's own are stale, and must go.  An excluded
# path is never deleted, so a secondary kept the write-ahead log of a map search database whose database the
# primary had replaced, and SQLite would apply that log to the new database.  (rsync keeps its own partial
# directory itself.)
UNFINISHED_PATTERNS = (".partial", "*.part", "*.aria2", "*.ytdl", "*.db-wal", "*.db-shm")


class SyncError(Exception):
    pass


class SyncCancelled(SyncError):
    pass


def default_status() -> dict:
    return dict(
        state="idle",  # 'idle', 'running', or 'error'
        phase=None,  # 'checks', 'snapshot', 'files', 'database', 'starting', 'purge'
        started_at=None,
        finished_at=None,
        last_success_at=None,
        last_error=None,
        primary_url=None,
        primary_version=None,
        percent=0,
        bytes_transferred=0,
        files_transferred=0,
        files_deleted=0,
        trash_bytes=0,
        warnings=[],
    )


_status = None
# True once the state file was read or written: until then the drive may not be mounted, and what is in memory must
# not be mistaken for (or saved over) what the last sync recorded.
_status_from_file = False
_status_lock = threading.Lock()
_run_lock = threading.Lock()
_cancel = threading.Event()


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _state_file() -> Path:
    return get_media_directory() / STATE_FILE


def get_status() -> dict:
    """The progress and outcome of the sync.  Read from the state file, so a restarted Controller still knows when
    the last sync succeeded; read again until that works, as the Controller may start before the drive is mounted."""
    global _status, _status_from_file
    with _status_lock:
        if _status is None:
            _status = default_status()
        if not _status_from_file:
            try:
                saved = yaml.safe_load(checked_path(_state_file()).read_text())
                if isinstance(saved, dict):
                    _status = default_status()
                    _status.update({k: v for k, v in saved.items() if k in _status})
                    _status_from_file = True
            except (OSError, yaml.YAMLError, SyncError):
                pass
        return dict(_status)


def update_status(save: bool = False, **changes) -> dict:
    """Change the status.  `save` also writes it to the state file (not done for every line of progress)."""
    get_status()
    with _status_lock:
        _status.update(changes)
        status = dict(_status)
    if save:
        global _status_from_file
        try:
            write_file(_state_file(), yaml.safe_dump(status))
            _status_from_file = True
        except (OSError, SyncError) as e:
            logger.warning("Could not save the sync state: %s", e)
    return status


def checked_path(path: Path) -> Path:
    """`path`, which is inside the media directory, refused if it or a directory on the way to it is a symbolic
    link.  The Controller runs as root, and the media directory belongs to another user: a link there would have
    root read, write or delete somewhere else."""
    current = get_media_directory()
    for part in path.relative_to(current).parts:
        current = current / part
        if current.is_symlink():
            raise SyncError(f"{current} is a symbolic link")
    return path


def write_file(file: Path, text: str):
    """Write `file` in the media directory without following a link: to a new file of its own, renamed into
    place.  It belongs to the media directory's owner, like everything else in the library."""
    checked_path(file)
    owner = get_media_directory().stat()
    temporary = file.with_name(f".{file.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(descriptor, "w") as fh:
        with contextlib.suppress(PermissionError):
            os.fchown(fh.fileno(), owner.st_uid, owner.st_gid)
        fh.write(text)
    os.replace(temporary, file)


def make_directory(directory: Path) -> Path:
    """Make a directory in the media directory that belongs to the media directory's owner, as rsync (which does
    not run as root) must write into it."""
    media_directory = get_media_directory()
    checked_path(directory)
    owner = media_directory.stat()
    missing = [i for i in (directory, *directory.parents) if media_directory in i.parents and not i.exists()]
    directory.mkdir(parents=True, exist_ok=True)
    for path in missing:
        with contextlib.suppress(PermissionError):
            os.chown(path, owner.st_uid, owner.st_gid, follow_symlinks=False)
    return directory


def read_sync_config() -> dict:
    try:
        return yaml.safe_load((get_media_directory() / "config/sync.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}


def get_delete_after_days(config: dict) -> Optional[int]:
    """Days a file the primary deleted is kept; None means such files are never deleted."""
    if "delete_after_days" not in config:
        return DEFAULT_DELETE_AFTER_DAYS
    days = config["delete_after_days"]
    return None if days is None else max(0, int(days))


def rsync_url(primary_url: str, path: str = "") -> str:
    """The primary's rsync daemon address for a path in its media directory."""
    host = urlparse(primary_url).hostname
    if not host:
        raise SyncError(f"Invalid primary address: {primary_url!r}")
    if ":" in host:
        host = f"[{host}]"
    return f"rsync://{host}:{get_rsyncd_port()}/media/{path}"


def timeout_arguments() -> list:
    return [f"--contimeout={RSYNC_CONNECT_TIMEOUT_SECONDS}", f"--timeout={RSYNC_IO_TIMEOUT_SECONDS}"]


def rsync_literal(path: str) -> str:
    """`path` as an rsync pattern that matches only itself (rsync reads `* ? [ \\` as wildcards)."""
    return re.sub(r"([*?\[\\])", r"\\\1", path)


def build_files_command(primary_url: str, media_directory: Path, trash: Optional[Path],
                        excluded_directories: list = None, playlists_destinations: list = ("playlists",)) -> list:
    """The rsync arguments (without `rsync`) that make `media_directory` a copy of the primary's.

    `trash` is where deleted and replaced files are moved; None never deletes.  `playlists_destinations` are the
    playlists directories of the primary (hard links there, which would arrive as full copies) and of this machine
    (its own links, which must not be deleted)."""
    arguments = [
        # Not --archive: owner and group are this machine's, and a library holds no devices.
        "--recursive", "--perms", "--times",
        # A link is copied only if it points inside the library.  One that points elsewhere would, on this machine,
        # point at this machine's files, which the web server would then serve.
        "--links", "--safe-links",
        "--partial", f"--partial-dir={PARTIAL_DIRECTORY}",
        "--info=progress2,stats2", "--no-human-readable",
        *timeout_arguments(),
    ]
    if trash is not None:
        # An excluded path is never deleted, so the trash and this machine's own files are safe from --delete.
        arguments.extend(["--delete", "--backup", f"--backup-dir={trash}"])
    arguments.extend(f"--exclude={i}" for i in LOCAL_PATHS)
    for playlists in dict.fromkeys(str(i or "").strip("/") for i in playlists_destinations):
        if playlists:
            arguments.append(f"--exclude=/{rsync_literal(playlists)}")
    arguments.extend(f"--filter=H {i}" for i in UNFINISHED_PATTERNS)
    if trash is None:
        # Nothing of the library is deleted, but the secondary's stale unfinished files must still go: a log left
        # beside a database the primary replaced would be applied to it.  Only those are at risk (R); everything
        # else is protected (P) from the --delete that removes them.
        arguments.append("--delete")
        for pattern in UNFINISHED_PATTERNS:
            # The pattern itself, and what is inside it when it is a folder (".partial").
            arguments.extend([f"--filter=R {pattern}", f"--filter=R {pattern}/**"])
        arguments.append("--filter=P *")
    # Folders the owner chose not to copy.
    for directory in excluded_directories or []:
        if directory := str(directory).strip("/"):
            arguments.append(f"--exclude=/{rsync_literal(directory)}")
    arguments.extend([rsync_url(primary_url), f"{media_directory}/"])
    return arguments


def build_database_command(primary_url: str, media_directory: Path) -> list:
    """The rsync arguments that fetch the primary's database snapshot to `INCOMING_DATABASE`."""
    return [
        "--times", "--partial", "--info=progress2,stats2", "--no-human-readable",
        *timeout_arguments(),
        # The database in use is what the snapshot is built from, so only what differs is sent.
        f"--copy-dest={media_directory / 'config'}",
        # Never judged the same by size and time: two databases of one size, written in the same second, are common
        # (a database grows a page at a time), and the secondary would keep its own.
        "--ignore-times",
        rsync_url(primary_url, SNAPSHOT_PATH), str(media_directory / INCOMING_DATABASE),
    ]


PROGRESS = re.compile(r"^\s*(\d+)\s+(\d+)%")
STATS = {
    "files_transferred": re.compile(r"^Number of regular files transferred: (\d+)"),
    "files_deleted": re.compile(r"^Number of deleted files: (\d+)"),
}


def parse_rsync_line(line: str) -> dict:
    """What a line of rsync's output says about its progress, as status changes."""
    if match := PROGRESS.match(line):
        return dict(bytes_transferred=int(match.group(1)), percent=int(match.group(2)))
    for key, pattern in STATS.items():
        if match := pattern.match(line.replace(",", "")):
            return {key: int(match.group(1))}
    return {}


# ---------------------------------------------------------------------------------------------------------------------
# What differs between a Raspberry Pi or Debian (systemd) and Docker.


class SystemdRunner:
    """rsync runs here as the wrolpi user, who owns the library; the API is a systemd unit."""

    def check(self):
        if not shutil.which("rsync"):
            raise SyncError("rsync is not installed")

    def stop_api(self):
        result = stop_service("wrolpi-api")
        if not result.get("success"):
            raise SyncError(f"Could not stop the API: {result.get('error')}")

    def start_api(self):
        start_service("wrolpi-api")

    def stop_rsync(self):
        """Nothing to do: rsync is the Controller's child, and systemd stops it with the Controller."""

    def rsync(self, arguments: list, on_line: Callable[[str], None]) -> int:
        command = ["runuser", "-u", "wrolpi", "--", "rsync", *arguments]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return _follow(process.stdout.read1, on_line, process.terminate, process.wait)


class DockerRunner:
    """rsync runs in a helper container made from the api container (its image, user and volumes), so it writes
    where the API reads.  The Controller does the rest in its own media directory, which must be the same one."""
    HELPER_NAME = _get_container_name("sync")

    def _api(self):
        return _get_client().containers.get(_get_container_name("api"))

    def check(self):
        if not can_manage_containers():
            raise SyncError("Docker management is not available")
        # Asked of the containers themselves: the paths Docker reports for one folder can differ.
        probe = make_directory(get_media_directory() / SYNC_DIRECTORY) / f".probe-{uuid.uuid4().hex}"
        write_file(probe, "")
        try:
            seen = self._api().exec_run(["test", "-e", str(probe)]).exit_code == 0
        finally:
            probe.unlink(missing_ok=True)
        if not seen:
            raise SyncError("The controller and api containers have different media directories; "
                            "give the controller service the api service's media volume")

    def stop_api(self):
        result = stop_container("api")
        if not result.get("success"):
            raise SyncError(f"Could not stop the API: {result.get('error')}")

    def start_api(self):
        start_container("api")

    def stop_rsync(self):
        """The helper is its own container: it outlives a Controller that stops, and goes on replacing files."""
        with contextlib.suppress(Exception):
            _get_client().containers.get(self.HELPER_NAME).remove(force=True)

    def rsync(self, arguments: list, on_line: Callable[[str], None]) -> int:
        client, api = _get_client(), self._api()
        self.stop_rsync()
        helper = client.containers.create(
            api.image.id, arguments, entrypoint="rsync", name=self.HELPER_NAME,
            user=api.attrs["Config"].get("User") or None, volumes_from=[api.name])
        try:
            # Attached, not followed through the logs: Docker's logs hold a line until it ends, and rsync's progress
            # for one large file is a single line, rewritten with carriage returns until the file is done.
            # Attached before it starts, so nothing it writes is missed.
            stream = helper.attach(stdout=True, stderr=True, stream=True)
            helper.start()

            def read(_: int = 0) -> bytes:
                return next(stream, b"")

            return _follow(read, on_line, helper.kill, lambda: helper.wait()["StatusCode"])
        finally:
            with contextlib.suppress(Exception):
                helper.remove(force=True)


def _follow(read: Callable, on_line: Callable[[str], None], stop: Callable, wait: Callable) -> int:
    """Hand rsync's output to `on_line` a line at a time (progress lines end in a carriage return).  Stops rsync
    as soon as the sync is cancelled, even while rsync is silent.  Returns rsync's exit code."""
    finished = threading.Event()

    def stop_when_cancelled():
        while not finished.is_set():
            if _cancel.wait(0.2):
                with contextlib.suppress(Exception):
                    stop()
                return

    watcher = threading.Thread(target=stop_when_cancelled, daemon=True)
    watcher.start()
    try:
        buffer = b""
        while chunk := read(65536):
            buffer += chunk
            *lines, buffer = re.split(rb"[\r\n]", buffer)
            for line in lines:
                if line.strip():
                    on_line(line.decode(errors="replace"))
        if buffer.strip():
            on_line(buffer.decode(errors="replace"))
        code = wait()
    finally:
        finished.set()
    if _cancel.is_set():
        raise SyncCancelled("The sync was cancelled")
    return code


def get_runner():
    return DockerRunner() if is_docker_mode() else SystemdRunner()


# ---------------------------------------------------------------------------------------------------------------------
# The primary's and this machine's API.


def _local_api_url() -> str:
    return "http://api:8081" if is_docker_mode() else "http://127.0.0.1:8081"


def _get_json(url: str, timeout: float = 30) -> dict:
    # WROLPi serves HTTPS with its own certificate authority; on a trusted LAN the primary is not verified.
    response = httpx.get(url, timeout=timeout, verify=False)
    response.raise_for_status()
    return response.json()


def get_primary_info(primary_url: str) -> dict:
    return _get_json(f"{primary_url}/api/sync/info")


def get_local_info() -> dict:
    return _get_json(f"{_local_api_url()}/api/sync/info")


def request_snapshot(primary_url: str) -> dict:
    """Ask the primary for a database snapshot and wait for it.  Returns the snapshot's status."""
    before = _get_json(f"{primary_url}/api/sync/status").get("snapshot") or {}
    response = httpx.post(f"{primary_url}/api/sync/snapshot", timeout=30, verify=False)
    if response.status_code >= 400:
        with contextlib.suppress(Exception):
            raise SyncError(f"The primary made no snapshot: {response.json()['error']}")
        raise SyncError(f"The primary made no snapshot: HTTP {response.status_code}")
    deadline = time.monotonic() + SNAPSHOT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        _check_cancel()
        snapshot = _get_json(f"{primary_url}/api/sync/status").get("snapshot") or {}
        finished = snapshot.get("finished_at")
        if not snapshot.get("requested") and snapshot.get("state") != "running" \
                and finished and finished != before.get("finished_at"):
            if snapshot.get("state") == "error":
                raise SyncError(f"The primary made no snapshot: {snapshot.get('last_error')}")
            return snapshot
        time.sleep(2)
    raise SyncError("The primary did not finish its snapshot in time")


def wait_for_api(timeout: float = API_START_TIMEOUT_SECONDS) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with contextlib.suppress(Exception):
            if httpx.get(f"{_local_api_url()}/api/echo", timeout=5).status_code == 200:
                return True
        time.sleep(2)
    return False


# ---------------------------------------------------------------------------------------------------------------------
# The steps.


def _check_cancel():
    if _cancel.is_set():
        raise SyncCancelled("The sync was cancelled")
    if is_wrol_mode():
        raise SyncCancelled("WROL Mode was enabled")


def skip_reason(config: dict = None) -> Optional[str]:
    """Why a sync cannot start now, or None."""
    config = read_sync_config() if config is None else config
    if config.get("role") != "secondary":
        return "This WROLPi is not a secondary"
    if not config.get("primary_url"):
        return "No primary is configured"
    if is_wrol_mode():
        return "WROL Mode is enabled"
    if not (get_media_directory() / "config/controller.yaml").exists():
        return "The media directory is not mounted"
    if _run_lock.locked():
        return "A sync is already running"
    return None


def check_primary(primary: dict, local: dict):
    """Refuse a primary whose library or database this secondary must not take."""
    if primary.get("role") != "primary":
        raise SyncError("The primary address is not a primary WROLPi")
    if not primary.get("media_mounted"):
        # Its media directory would look like an empty library.
        raise SyncError("The primary's media directory is not mounted")
    for key, name in (("version", "WROLPi version"), ("database_revision", "database migration")):
        if not primary.get(key) or primary.get(key) != local.get(key):
            raise SyncError(f"The primary's {name} ({primary.get(key)}) is not this WROLPi's ({local.get(key)}); "
                            "upgrade both to the same version")
    if not primary.get("media_directory") or primary.get("media_directory") != local.get("media_directory"):
        # The database names every file by its full path.
        raise SyncError(f"The primary's media directory ({primary.get('media_directory')}) is not this WROLPi's "
                        f"({local.get('media_directory')}); its database would find no file here")


def replace_database(media_directory: Path):
    """Put the fetched snapshot in the database's place.

    The old write-ahead log must be gone first: left beside the new database it would be applied to it.  It is
    emptied by a checkpoint rather than only deleted, so a run that stops between the two steps leaves the old
    database complete."""
    database = checked_path(media_directory / "config/wrolpi.db")
    incoming = checked_path(media_directory / INCOMING_DATABASE)
    # Immutable: read without making a -wal and -shm beside it, which would be left behind when it is moved.
    with contextlib.closing(sqlite3.connect(f"file:{incoming}?mode=ro&immutable=1", uri=True)) as connection:
        if connection.execute("PRAGMA schema_version").fetchone()[0] == 0:
            raise SyncError("The snapshot from the primary is not a database")
    if database.is_file():
        with contextlib.closing(sqlite3.connect(database, timeout=60)) as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    for suffix in ("-wal", "-shm"):
        database.with_name(f"wrolpi.db{suffix}").unlink(missing_ok=True)
    os.replace(incoming, database)


def directory_size(directory: Path) -> int:
    total = 0
    for root, _, names in os.walk(directory):
        for name in names:
            with contextlib.suppress(OSError):
                total += os.lstat(os.path.join(root, name)).st_size
    return total


def purge_trash(media_directory: Path, delete_after_days: Optional[int], today: datetime.date = None,
                min_free_bytes: int = MIN_FREE_BYTES) -> list:
    """Remove the trash folders that have waited `delete_after_days` and, while the drive is nearly full, the
    oldest of the rest.  A folder is as old as its name says, whatever its files' times are.  Returns their names."""
    trash = media_directory / TRASH_DIRECTORY
    if trash.is_symlink() or not trash.is_dir():
        return []
    today = today or datetime.date.today()
    dated = []
    for folder in trash.iterdir():
        if folder.is_symlink() or not folder.is_dir():
            continue
        with contextlib.suppress(ValueError):
            dated.append((datetime.date.fromisoformat(folder.name), folder))
    purged = []
    for day, folder in sorted(dated):
        expired = delete_after_days is not None and (today - day).days >= delete_after_days
        nearly_full = shutil.disk_usage(media_directory).free < min_free_bytes
        if not expired and not nearly_full:
            continue
        logger.info("Removing the sync trash of %s (%s)", folder.name, "expired" if expired else "drive nearly full")
        shutil.rmtree(folder, ignore_errors=True)
        purged.append(folder.name)
    return purged


def run_sync(runner=None) -> dict:
    """Make this secondary a copy of its primary.  Returns the final status."""
    config = read_sync_config()
    if reason := skip_reason(config):
        logger.info("Not syncing: %s", reason)
        return update_status(last_error=reason)
    if not _run_lock.acquire(blocking=False):
        return update_status(last_error="A sync is already running")

    runner = runner or get_runner()
    media_directory = get_media_directory()
    api_stopped = False
    warnings = []
    _cancel.clear()
    # Everything after the lock is taken is inside the `try`: whatever goes wrong, the lock is released.
    try:
        primary_url = str(config["primary_url"]).rstrip("/")
        update_status(save=True, state="running", phase="checks", started_at=_now(), finished_at=None,
                      last_error=None, primary_url=primary_url, primary_version=None, percent=0,
                      bytes_transferred=0, files_transferred=0, files_deleted=0, warnings=[])
        logger.warning("Syncing from the primary %s", primary_url)
        delete_after_days = get_delete_after_days(config)
        runner.check()
        primary, local = get_primary_info(primary_url), get_local_info()
        update_status(primary_version=primary.get("version"))
        check_primary(primary, local)
        _check_cancel()

        update_status(phase="snapshot")
        snapshot = request_snapshot(primary_url)
        # The trash is what fills the drive, and a full drive fails every run: make room before the copy, not
        # only after a run that succeeded.
        purge_trash(media_directory, delete_after_days)
        if shutil.disk_usage(media_directory).free - int(snapshot.get("size") or 0) < MIN_FREE_BYTES:
            raise SyncError("Not enough free space for the primary's database")
        _check_cancel()

        make_directory(media_directory / SYNC_DIRECTORY / "incoming")
        # The primary's wrolpi.yaml names its playlists directory, which must be left out of the copy.
        code = runner.rsync(["--times", *timeout_arguments(), rsync_url(primary_url, "config/wrolpi.yaml"),
                             str(media_directory / PRIMARY_WROLPI_CONFIG)], lambda _: None)
        if code != 0:
            raise SyncError(f"rsync of the primary's wrolpi.yaml failed with exit code {code}")
        write_file(media_directory / PRIMARY_INFO, yaml.safe_dump(primary))
        playlists = [_read_yaml(media_directory / i).get("playlists_destination") or "playlists"
                     for i in (PRIMARY_WROLPI_CONFIG, "config/wrolpi.yaml")]

        update_status(save=True, phase="files")
        runner.stop_api()
        api_stopped = True

        trash = None
        if delete_after_days is not None:
            trash = media_directory / TRASH_DIRECTORY / datetime.date.today().isoformat()
        command = build_files_command(primary_url, media_directory, trash,
                                      config.get("sync_excluded_directories"), playlists)
        code = runner.rsync(command, lambda line: update_status(**parse_rsync_line(line)))
        if code in (RSYNC_PARTIAL, RSYNC_VANISHED):
            warnings.append("Some files changed on the primary during the sync, or could not be copied; "
                            "the next sync copies them")
        elif code != 0:
            raise SyncError(f"rsync failed with exit code {code}")
        _check_cancel()

        update_status(save=True, phase="database", percent=0)
        code = runner.rsync(
            build_database_command(primary_url, media_directory),
            lambda line: update_status(**{k: v for k, v in parse_rsync_line(line).items() if k == "percent"}))
        if code != 0:
            raise SyncError(f"rsync of the database failed with exit code {code}")
        # After this the run cannot be undone by stopping it.
        replace_database(media_directory)

        update_status(save=True, phase="starting", percent=100)
        runner.start_api()
        api_stopped = False
        if not wait_for_api():
            warnings.append("The API did not answer after the sync")

        update_status(phase="purge")
        purge_trash(media_directory, delete_after_days)
    except SyncCancelled as e:
        logger.warning("Sync stopped: %s", e)
        return _finish(runner, api_stopped, state="idle", last_error=str(e), warnings=warnings)
    except Exception as e:
        logger.error("Sync failed", exc_info=e)
        return _finish(runner, api_stopped, state="error", last_error=str(e) or type(e).__name__, warnings=warnings)

    logger.warning("Synced from the primary %s", config["primary_url"])
    return _finish(runner, api_stopped, state="idle", last_error=None, last_success_at=_now(), warnings=warnings)


def _finish(runner, api_stopped: bool, **changes) -> dict:
    """Whatever happened, the API runs again and the lock is free.  The outcome is recorded before the lock is
    freed: a status that says "running" while no sync holds the lock is taken for an interrupted sync."""
    try:
        if api_stopped:
            runner.start_api()
        trash = get_media_directory() / TRASH_DIRECTORY
        return update_status(save=True, phase=None, finished_at=_now(),
                             trash_bytes=directory_size(trash) if trash.is_dir() and not trash.is_symlink() else 0,
                             **changes)
    finally:
        _run_lock.release()


def _read_yaml(file: Path) -> dict:
    try:
        return yaml.safe_load(file.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}


def request_cancel():
    """Stop the running sync at its next step, or its rsync at once."""
    if _run_lock.locked():
        _cancel.set()


def recover_interrupted_sync(runner=None):
    """A status that says "running" while no sync holds the lock was left by a Controller that stopped during a
    sync, which left the API stopped: start it, and say the sync was interrupted.  Looked at by every tick of the
    schedule, before it starts anything, and so also once the state file can be read after the drive mounts."""
    status = get_status()
    if status["state"] != "running" or _run_lock.locked():
        return
    logger.warning("A sync was interrupted; starting the API")
    runner = runner or get_runner()
    # Before the API starts: nothing may still be replacing the library under it.
    with contextlib.suppress(Exception):
        runner.stop_rsync()
    with contextlib.suppress(Exception):
        runner.start_api()
    update_status(save=True, state="error", phase=None, finished_at=_now(),
                  last_error="The sync was interrupted")


# ---------------------------------------------------------------------------------------------------------------------
# The schedule.


def local_now() -> datetime.datetime:
    """Now, in WROLPi's timezone (wrolpi.yaml), or the system's when none is set."""
    timezone = _read_yaml(get_media_directory() / "config/wrolpi.yaml").get("timezone")
    if timezone:
        with contextlib.suppress(zoneinfo.ZoneInfoNotFoundError, ValueError):
            return datetime.datetime.now(zoneinfo.ZoneInfo(timezone))
    return datetime.datetime.now().astimezone()


def _parse_time(value) -> Optional[datetime.time]:
    with contextlib.suppress(TypeError, ValueError):
        return datetime.time.fromisoformat(str(value))
    return None


def in_window(start: Optional[str], end: Optional[str], now: datetime.time) -> bool:
    """True if `now` is within the daily window from `start` to `end`, which may run past midnight."""
    start, end = _parse_time(start), _parse_time(end)
    if start is None or end is None:
        return False
    if start <= end:
        return start <= now < end
    return now >= start or now < end


def sync_is_due(config: dict, status: dict, now: datetime.datetime) -> bool:
    """True if the daily sync window is open and the last sync finished long enough ago.  No window: never (a sync
    only runs when asked)."""
    if not in_window(config.get("window_start"), config.get("window_end"), now.time()):
        return False
    with contextlib.suppress(TypeError, ValueError):
        finished_at = datetime.datetime.fromisoformat(status["finished_at"])
        return (now - finished_at).total_seconds() >= SYNC_REPEAT_SECONDS
    return True


def schedule_tick():
    """Start a sync if one is due.  A sync that cannot start (WROL Mode, a primary, no primary) is not due."""
    recover_interrupted_sync()
    config = read_sync_config()
    if skip_reason(config) is not None:
        return
    if sync_is_due(config, get_status(), local_now()):
        logger.info("The sync window is open")
        run_sync()


async def sync_schedule_loop():
    """Sync within the daily window for as long as the Controller runs."""
    while True:
        try:
            await asyncio.to_thread(schedule_tick)
        except Exception as e:
            logger.error("The sync schedule failed", exc_info=e)
        await asyncio.sleep(SCHEDULE_INTERVAL_SECONDS)
