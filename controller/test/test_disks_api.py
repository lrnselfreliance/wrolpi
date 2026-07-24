"""
Integration tests for Controller disks API endpoints.

The API writes fstab.yaml and asks wrolpi-mounts.service to reconcile.
Tests inject:

- a FakeMountExecutor in place of the production SubprocessMountExecutor,
- a fake ``_trigger_reconcile`` that simulates the service by running the
  real Reconciler against the fake executor + a tmp_path fstab.yaml.

The only mocks are ``mock.patch`` for the read helpers (get_block_devices,
get_mounts, get_uuid, SMART) that touch the host's real disks.  The
mount/unmount/fstab paths use real I/O against tmp_path and the
FakeMountExecutor.
"""

from pathlib import Path
from unittest import mock

import pytest

from controller.lib import fstab_yaml
from controller.lib.mount_executor import FakeMountExecutor
from controller.lib.reconciler import Reconciler


@pytest.fixture
def disks_env(monkeypatch, tmp_path):
    """Replace production wiring with a real Reconciler driving a fake
    executor against a tmp_path fstab.yaml.  Returns ``(fake, fstab_path)``.

    Calling the API mutates the real fstab.yaml on disk and then runs the
    real Reconciler.apply() — verifying the same code path that boot uses.
    """
    fstab_path = tmp_path / "fstab.yaml"
    managed_path = tmp_path / "managed"
    monkeypatch.setattr(fstab_yaml, "DEFAULT_PATH", fstab_path)

    fake = FakeMountExecutor()

    def fake_trigger():
        # Run the real reconciler.  This is exactly the work the service
        # would do when systemctl restarts it.
        Reconciler(
            executor=fake,
            fstab_path=fstab_path,
            managed_path=managed_path,
            wrolpi_uid=1001,
            wrolpi_gid=1001,
        ).apply()
        return True, None

    from controller.api import disks as disks_module
    monkeypatch.setattr(disks_module, "_executor", fake)
    monkeypatch.setattr(disks_module, "_trigger_reconcile", fake_trigger)

    return {"fake": fake, "fstab_path": fstab_path}


# --- Docker mode ----------------------------------------------------------

class TestDockerModeRejectsDisksEndpoints:
    """All /api/disks/* endpoints should return 501 in Docker mode."""

    @pytest.mark.parametrize("method,endpoint,payload", [
        ("get", "/api/disks", None),
        ("get", "/api/disks/mounts", None),
        ("post", "/api/disks/mount", {"device": "/dev/sda1", "mount_point": "/media/test"}),
        ("post", "/api/disks/unmount", {"mount_point": "/media/test"}),
        ("get", "/api/disks/fstab", None),
        ("post", "/api/disks/fstab", {"device": "/dev/sda1", "mount_point": "/media/test", "fstype": "ext4"}),
        ("delete", "/api/disks/fstab/media/test", None),
        ("get", "/api/disks/smart", None),
    ])
    def test_disks_endpoint_rejected_in_docker(
        self, test_client_docker_mode, method, endpoint, payload,
    ):
        client_call = getattr(test_client_docker_mode, method)
        response = client_call(endpoint, json=payload) if payload else client_call(endpoint)
        assert response.status_code == 501


# --- Read-only endpoints --------------------------------------------------

class TestDisksListEndpoint:

    def test_returns_list_in_native_mode(self, test_client):
        with mock.patch("controller.api.disks.get_block_devices", return_value=[]):
            response = test_client.get("/api/disks")
            assert response.status_code == 200
            assert isinstance(response.json(), list)


class TestMountsEndpoint:

    def test_returns_mounts(self, test_client):
        mock_mounts = [{"mount_point": "/media/wrolpi", "device": "/dev/sda1"}]
        with mock.patch("controller.api.disks.get_mounts", return_value=mock_mounts):
            response = test_client.get("/api/disks/mounts")
            assert response.status_code == 200
            assert response.json() == mock_mounts


# --- /api/disks/mount -----------------------------------------------------

class TestMountEndpoint:

    def test_mounts_drive_successfully(self, test_client, disks_env):
        with mock.patch("controller.api.disks.check_shadowed_data", return_value=None), \
                mock.patch("controller.api.disks.get_uuid", return_value="abc-123"):
            response = test_client.post(
                "/api/disks/mount",
                json={"device": "/dev/sda1", "mount_point": "/media/wrolpi/usb",
                      "fstype": "ext4"},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["device"] == "UUID=abc-123"
        assert body["mount_point"] == "/media/wrolpi/usb"
        # Drive is now in fstab.yaml AND live in the fake executor.
        assert disks_env["fake"].current_mount_points() == {"/media/wrolpi/usb"}
        data = fstab_yaml.load(disks_env["fstab_path"])
        assert data.mount_points() == {"/media/wrolpi/usb"}

    def test_returns_500_when_reconciler_fails(self, test_client, disks_env, monkeypatch):
        # Force the fake executor to refuse the mount; reconciler runs but
        # the live state will not include the mount point.
        disks_env["fake"].fail_for_mount = frozenset({"/media/wrolpi/usb"})
        with mock.patch("controller.api.disks.check_shadowed_data", return_value=None), \
                mock.patch("controller.api.disks.get_uuid", return_value="abc-123"):
            response = test_client.post(
                "/api/disks/mount",
                json={"device": "/dev/sda1", "mount_point": "/media/wrolpi/usb",
                      "fstype": "ext4"},
            )
        assert response.status_code == 500
        assert "did not mount" in response.json()["detail"]
        # The entry is still in fstab.yaml — it'll be retried next reconcile.
        assert fstab_yaml.load(disks_env["fstab_path"]).mount_points() == {"/media/wrolpi/usb"}

    def test_replaces_existing_entry_for_same_device(self, test_client, disks_env):
        # Seed fstab.yaml with an existing entry, then mount the same device
        # to a different path.  The old row should drop, not accumulate.
        from controller.lib.fstab_yaml import FstabEntry, FstabFile, save
        save(FstabFile(mounts=[FstabEntry(
            "UUID=abc-123", "/media/wrolpi/old", "ext4", "defaults")]),
            disks_env["fstab_path"])

        with mock.patch("controller.api.disks.check_shadowed_data", return_value=None), \
                mock.patch("controller.api.disks.get_uuid", return_value="abc-123"):
            response = test_client.post(
                "/api/disks/mount",
                json={"device": "/dev/sda1", "mount_point": "/media/wrolpi/new",
                      "fstype": "ext4"},
            )
        assert response.status_code == 200
        data = fstab_yaml.load(disks_env["fstab_path"])
        assert data.mount_points() == {"/media/wrolpi/new"}

    def test_shadowed_data_soft_blocks_mount(self, test_client, disks_env):
        shadowed = {"size_bytes": 1024, "entries": ["videos"]}
        with mock.patch("controller.api.disks.check_shadowed_data", return_value=shadowed):
            response = test_client.post(
                "/api/disks/mount",
                json={"device": "/dev/sda1", "mount_point": "/media/wrolpi/usb"},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["needs_force"] == "shadowed"
        # No fstab.yaml mutation.
        assert disks_env["fstab_path"].exists() is False
        assert disks_env["fake"].mount_calls == []

    def test_force_shadowed_overrides_soft_block(self, test_client, disks_env):
        shadowed = {"size_bytes": 1, "entries": ["a"]}
        with mock.patch("controller.api.disks.check_shadowed_data", return_value=shadowed) as chk, \
                mock.patch("controller.api.disks.get_uuid", return_value="abc-123"):
            response = test_client.post(
                "/api/disks/mount",
                json={
                    "device": "/dev/sda1",
                    "mount_point": "/media/wrolpi/usb",
                    "fstype": "ext4",
                    "force_shadowed": True,
                },
            )
        assert response.status_code == 200
        chk.assert_not_called()
        assert "/media/wrolpi/usb" in disks_env["fake"].current_mount_points()


# --- /api/disks/unmount ---------------------------------------------------

class TestUnmountEndpoint:

    def test_unmounts_and_removes_from_fstab(self, test_client, disks_env):
        # Seed: drive is live AND in fstab.yaml AND managed by reconciler.
        from controller.lib.fstab_yaml import FstabEntry, FstabFile, save
        save(FstabFile(mounts=[FstabEntry(
            "UUID=abc-123", "/media/wrolpi/usb", "ext4", "defaults")]),
            disks_env["fstab_path"])
        disks_env["fake"]._live.add("/media/wrolpi/usb")
        # Tell reconciler we own it (so a removal triggers an unmount).
        (disks_env["fstab_path"].parent / "managed").write_text(
            "/media/wrolpi/usb\n")

        response = test_client.post(
            "/api/disks/unmount",
            json={"mount_point": "/media/wrolpi/usb"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["removed_from_fstab"] is True
        # Live unmounted, fstab.yaml empty.
        assert disks_env["fake"].current_mount_points() == set()
        assert fstab_yaml.load(disks_env["fstab_path"]).mounts == []

    def test_unmount_returns_500_when_still_mounted(self, test_client, disks_env):
        # Reconciler refuses the unmount (e.g. busy) — the direct fallback
        # fails the same way; surface the failure.
        disks_env["fake"]._live.add("/media/wrolpi/usb")
        disks_env["fake"].fail_for_unmount = frozenset({"/media/wrolpi/usb"})
        (disks_env["fstab_path"].parent / "managed").write_text(
            "/media/wrolpi/usb\n")

        response = test_client.post(
            "/api/disks/unmount",
            json={"mount_point": "/media/wrolpi/usb"},
        )
        assert response.status_code == 500
        assert "still mounted" in response.json()["detail"]

    def test_unmount_foreign_mount_falls_back_to_direct_umount(
        self, test_client, disks_env,
    ):
        # A udisks2 desktop automount: live, but never in fstab.yaml and
        # never claimed by the reconciler.  The reconciler will not touch
        # it, so the endpoint must unmount it directly.
        foreign = "/media/wrolpi/31a8ecf1-c00b-4691-b26f-b0966073659f"
        disks_env["fake"]._live.add(foreign)

        response = test_client.post(
            "/api/disks/unmount",
            json={"mount_point": foreign},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["removed_from_fstab"] is False
        assert disks_env["fake"].current_mount_points() == set()

    @pytest.mark.parametrize("mount_point", [
        "/media",            # not strictly under /media/
        "/media_evil",       # prefix-collides with /media
    ])
    def test_unmount_rejects_paths_outside_media(
        self, test_client, disks_env, mount_point,
    ):
        response = test_client.post(
            "/api/disks/unmount",
            json={"mount_point": mount_point},
        )
        assert response.status_code == 400
        assert disks_env["fake"].unmount_calls == []

    def test_unmount_reserved_mount_point_rejected(self, test_client, disks_env):
        # The onboarding temp mount belongs to the Controller itself.
        disks_env["fake"]._live.add("/media/wrolpi_temp_onboarding")

        response = test_client.post(
            "/api/disks/unmount",
            json={"mount_point": "/media/wrolpi_temp_onboarding"},
        )
        assert response.status_code == 400
        assert "reserved" in response.json()["detail"].lower()
        # No umount was attempted, directly or via the reconciler.
        assert disks_env["fake"].unmount_calls == []
        assert disks_env["fake"].current_mount_points() == {
            "/media/wrolpi_temp_onboarding"}


class TestUnmountPrimaryEndpoint:
    """Unmounting the primary drive stops the API service, then umounts
    directly (the reconciler never manages the primary mount).  The
    /etc/fstab entry is left alone so a reboot restores the mount."""

    @pytest.fixture
    def primary_env(self, disks_env):
        with mock.patch("controller.api.disks.get_media_directory",
                        return_value=Path("/media/wrolpi")), \
             mock.patch("controller.api.disks.stop_service",
                        return_value={"success": True}) as stop:
            yield {**disks_env, "stop_service": stop}

    @pytest.mark.parametrize("mount_point", [
        "/media/wrolpi",
        "/media/wrolpi/../wrolpi",  # normalizes to the primary
    ])
    def test_unmount_primary_stops_api_and_unmounts(
        self, test_client, primary_env, mount_point,
    ):
        primary_env["fake"]._live.add("/media/wrolpi")

        response = test_client.post(
            "/api/disks/unmount",
            json={"mount_point": mount_point},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["removed_from_fstab"] is False
        assert body["stopped_services"] == ["wrolpi-api"]
        primary_env["stop_service"].assert_called_once_with("wrolpi-api")
        assert primary_env["fake"].current_mount_points() == set()

    def test_unmount_primary_returns_500_when_still_mounted(
        self, test_client, primary_env,
    ):
        # umount fails (e.g. busy) — surface the failure, but the service
        # stop should still have been attempted first.
        primary_env["fake"]._live.add("/media/wrolpi")
        primary_env["fake"].fail_for_unmount = frozenset({"/media/wrolpi"})

        response = test_client.post(
            "/api/disks/unmount",
            json={"mount_point": "/media/wrolpi"},
        )
        assert response.status_code == 500
        assert "still mounted" in response.json()["detail"]
        primary_env["stop_service"].assert_called_once_with("wrolpi-api")

    def test_unmount_primary_stop_failure_still_unmounts(
        self, test_client, primary_env,
    ):
        # A failed service stop (e.g. unit not installed) must not block
        # the unmount; the umount result decides success.
        primary_env["fake"]._live.add("/media/wrolpi")
        primary_env["stop_service"].return_value = {
            "success": False, "error": "unit not found"}

        response = test_client.post(
            "/api/disks/unmount",
            json={"mount_point": "/media/wrolpi"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["stopped_services"] == []
        assert primary_env["fake"].current_mount_points() == set()


# --- /api/disks/fstab read endpoint ---------------------------------------

class TestFstabReadEndpoint:

    def test_returns_empty_when_no_fstab_yaml(self, test_client, disks_env):
        response = test_client.get("/api/disks/fstab")
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_entries_in_legacy_shape(self, test_client, disks_env):
        from controller.lib.fstab_yaml import FstabEntry, FstabFile, save
        save(FstabFile(mounts=[
            FstabEntry("UUID=abc", "/media/wrolpi/usb", "ext4", "defaults"),
        ]), disks_env["fstab_path"])
        response = test_client.get("/api/disks/fstab")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["type"] == "mount"
        assert body[0]["device"] == "UUID=abc"
        assert body[0]["mount_point"] == "/media/wrolpi/usb"


# --- /api/disks/fstab POST / DELETE (no reconcile) ------------------------

class TestFstabMutateEndpoints:
    """POST and DELETE on /fstab modify fstab.yaml without triggering a
    reconcile — used to stage changes without immediately applying."""

    def test_post_adds_entry_to_fstab_only(self, test_client, disks_env):
        with mock.patch("controller.api.disks.get_uuid", return_value="abc-123"):
            response = test_client.post(
                "/api/disks/fstab",
                json={"device": "/dev/sda1",
                      "mount_point": "/media/wrolpi/usb",
                      "fstype": "ext4"},
            )
        assert response.status_code == 200
        assert response.json()["device"] == "UUID=abc-123"
        # fstab.yaml updated, but the executor was NOT asked to mount.
        assert fstab_yaml.load(disks_env["fstab_path"]).mount_points() == {"/media/wrolpi/usb"}
        assert disks_env["fake"].mount_calls == []

    def test_delete_removes_entry_from_fstab_only(self, test_client, disks_env):
        from controller.lib.fstab_yaml import FstabEntry, FstabFile, save
        save(FstabFile(mounts=[
            FstabEntry("UUID=abc", "/media/wrolpi/usb", "ext4", "defaults"),
            FstabEntry("UUID=def", "/media/wrolpi/other", "ext4", "defaults"),
        ]), disks_env["fstab_path"])

        response = test_client.delete("/api/disks/fstab/media/wrolpi/usb")
        assert response.status_code == 200
        # Other entry preserved.
        remaining = fstab_yaml.load(disks_env["fstab_path"]).mount_points()
        assert remaining == {"/media/wrolpi/other"}
        # No unmount issued — DELETE is config-only.
        assert disks_env["fake"].unmount_calls == []

    def test_delete_returns_404_for_missing_entry(self, test_client, disks_env):
        response = test_client.delete("/api/disks/fstab/media/missing")
        assert response.status_code == 404


# --- Primary mount persistence (/etc/fstab, not fstab.yaml) ----------------

class TestPrimaryMountPersist:
    """The primary mount (/media/wrolpi) persists via the host's /etc/fstab,
    not fstab.yaml: the wrolpi-mounts reconciler refuses to manage it
    (RESERVED_MOUNT_POINTS), so a fstab.yaml entry would never be applied."""

    @pytest.fixture(autouse=True)
    def primary_media_dir(self, monkeypatch):
        """conftest isolates MEDIA_DIRECTORY to a tmp dir; these tests need the
        real primary mount point so the endpoints route to /etc/fstab."""
        monkeypatch.setenv("MEDIA_DIRECTORY", "/media/wrolpi")

    def test_post_primary_routes_to_etc_fstab(self, test_client, disks_env):
        with mock.patch(
            "controller.api.disks.add_etc_fstab_entry",
            return_value={"success": True, "device": "UUID=abc-123",
                          "mount_point": "/media/wrolpi"},
        ) as add_etc:
            response = test_client.post(
                "/api/disks/fstab",
                json={"device": "/dev/sdb2",
                      "mount_point": "/media/wrolpi",
                      "fstype": "ntfs"},
            )
        assert response.status_code == 200
        assert response.json()["device"] == "UUID=abc-123"
        add_etc.assert_called_once()
        # fstab.yaml must NOT contain the primary mount.
        assert fstab_yaml.load(disks_env["fstab_path"]).mount_points() == set()

    def test_post_primary_reports_etc_fstab_failure(self, test_client, disks_env):
        with mock.patch(
            "controller.api.disks.add_etc_fstab_entry",
            return_value={"success": False, "error": "WROL Mode is enabled"},
        ):
            response = test_client.post(
                "/api/disks/fstab",
                json={"device": "/dev/sdb2",
                      "mount_point": "/media/wrolpi",
                      "fstype": "ntfs"},
            )
        assert response.status_code == 500
        assert "WROL Mode" in response.json()["detail"]

    def test_delete_primary_routes_to_etc_fstab(self, test_client, disks_env):
        with mock.patch(
            "controller.api.disks.remove_etc_fstab_entry",
            return_value={"success": True, "mount_point": "/media/wrolpi"},
        ) as remove_etc:
            response = test_client.delete("/api/disks/fstab/media/wrolpi")
        assert response.status_code == 200
        remove_etc.assert_called_once_with("/media/wrolpi")

    def test_delete_primary_missing_returns_404(self, test_client, disks_env):
        with mock.patch(
            "controller.api.disks.remove_etc_fstab_entry",
            return_value={"success": False,
                          "error": "No entry found for /media/wrolpi"},
        ):
            response = test_client.delete("/api/disks/fstab/media/wrolpi")
        assert response.status_code == 404

    def test_mount_primary_mounts_directly_and_persists_to_etc_fstab(
            self, test_client, disks_env):
        """POST /disks/mount for the primary mount bypasses fstab.yaml/the
        reconciler entirely: mount_drive + /etc/fstab, and any stale
        fstab.yaml phantom entry is removed."""
        from controller.lib.fstab_yaml import FstabEntry, FstabFile, save
        # Phantom left by an older Controller: reconciler only ever skips it.
        save(FstabFile(mounts=[
            FstabEntry("UUID=abc", "/media/wrolpi", "ntfs", "defaults"),
        ]), disks_env["fstab_path"])

        with mock.patch("controller.api.disks.mount_drive",
                        return_value={"success": True,
                                      "mount_point": "/media/wrolpi"}) as m_mount, \
                mock.patch("controller.api.disks.add_etc_fstab_entry",
                           return_value={"success": True, "device": "UUID=abc",
                                         "mount_point": "/media/wrolpi"}) as m_persist:
            response = test_client.post(
                "/api/disks/mount",
                json={"device": "/dev/sdb2",
                      "mount_point": "/media/wrolpi",
                      "fstype": "ntfs",
                      "force_shadowed": True},
            )
        assert response.status_code == 200
        assert response.json()["persisted"] is True
        m_mount.assert_called_once()
        m_persist.assert_called_once()
        # The reconciler's executor was never asked to mount anything.
        assert disks_env["fake"].mount_calls == []
        # The phantom fstab.yaml entry was cleaned up.
        assert fstab_yaml.load(disks_env["fstab_path"]).mount_points() == set()

    def test_mount_primary_failure_returns_500(self, test_client, disks_env):
        with mock.patch("controller.api.disks.mount_drive",
                        return_value={"success": False, "error": "unclean NTFS"}):
            response = test_client.post(
                "/api/disks/mount",
                json={"device": "/dev/sdb2",
                      "mount_point": "/media/wrolpi",
                      "fstype": "ntfs",
                      "force_shadowed": True},
            )
        assert response.status_code == 500
        assert "unclean NTFS" in response.json()["detail"]

    def test_list_hides_phantom_primary_yaml_entry(self, test_client, disks_env):
        """A reserved mount point in fstab.yaml is never applied, so it must
        not be reported as persistence."""
        from controller.lib.fstab_yaml import FstabEntry, FstabFile, save
        save(FstabFile(mounts=[
            FstabEntry("UUID=abc", "/media/wrolpi", "ntfs", "defaults"),
            FstabEntry("UUID=def", "/media/wrolpi/usb", "ext4", "defaults"),
        ]), disks_env["fstab_path"])
        with mock.patch("controller.api.disks.parse_etc_fstab", return_value=[]):
            response = test_client.get("/api/disks/fstab")
        assert response.status_code == 200
        assert [e["mount_point"] for e in response.json()] == ["/media/wrolpi/usb"]

    def test_delete_primary_cleans_phantom_yaml_entry(self, test_client, disks_env):
        """DELETE succeeds when only the phantom fstab.yaml entry exists."""
        from controller.lib.fstab_yaml import FstabEntry, FstabFile, save
        save(FstabFile(mounts=[
            FstabEntry("UUID=abc", "/media/wrolpi", "ntfs", "defaults"),
        ]), disks_env["fstab_path"])
        with mock.patch(
            "controller.api.disks.remove_etc_fstab_entry",
            return_value={"success": False,
                          "error": "No entry found for /media/wrolpi"},
        ):
            response = test_client.delete("/api/disks/fstab/media/wrolpi")
        assert response.status_code == 200
        assert fstab_yaml.load(disks_env["fstab_path"]).mount_points() == set()

    def test_list_includes_primary_from_etc_fstab(self, test_client, disks_env):
        etc_entries = [
            {"type": "comment", "line": "# /etc/fstab\n"},
            {"type": "mount", "device": "UUID=root", "mount_point": "/",
             "fstype": "ext4", "options": "defaults", "dump": "0", "pass": "1"},
            {"type": "mount", "device": "UUID=abc-123",
             "mount_point": "/media/wrolpi", "fstype": "ntfs",
             "options": "defaults,nofail", "dump": "0", "pass": "2"},
        ]
        with mock.patch("controller.api.disks.parse_etc_fstab",
                        return_value=etc_entries):
            response = test_client.get("/api/disks/fstab")
        assert response.status_code == 200
        body = response.json()
        mount_points = [e["mount_point"] for e in body]
        # The primary appears; unrelated system mounts (e.g. /) do not.
        assert mount_points == ["/media/wrolpi"]
        assert body[0]["device"] == "UUID=abc-123"


# --- SMART ----------------------------------------------------------------

class TestSmartEndpoints:

    def test_list_smart_when_not_available(self, test_client):
        with mock.patch("controller.api.disks.is_smart_available", return_value=False):
            response = test_client.get("/api/disks/smart")
            assert response.status_code == 200
            assert response.json()["available"] is False

    def test_list_smart_returns_drives(self, test_client):
        mock_drives = [{"device": "sda", "assessment": "PASS"}]
        with mock.patch("controller.api.disks.is_smart_available", return_value=True), \
                mock.patch("controller.api.disks.get_all_smart_status", return_value=mock_drives):
            response = test_client.get("/api/disks/smart")
            assert response.status_code == 200
            body = response.json()
            assert body["available"] is True
            assert len(body["drives"]) == 1
