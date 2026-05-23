"""
Tests for controller.lib.fstab_migration — one-time migration of
WROLPi-managed mount entries into fstab.yaml.

Sources:
  - /etc/fstab (older WROLPi versions)
  - /media/wrolpi/config/controller.yaml drives.mounts (intermediate)

Migration semantics:
  - Runs at most once per drive (gated by .fstab-migrated marker).
  - All /media/* entries (except /media/wrolpi and the temp onboarding
    mount) are candidates.
  - fstab.yaml gets each missing entry; existing entries are not touched.
  - /etc/fstab candidates are commented in place with a "migrated to
    fstab.yaml: " prefix.
  - controller.yaml has drives.mounts removed after migration.
  - /etc/fstab is backed up before modification.
"""

from pathlib import Path

import yaml

from controller.lib.fstab_migration import migrate_etc_fstab
from controller.lib.fstab_yaml import load as load_fstab_yaml


def _write(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


def _write_yaml(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data))
    return path


class TestMigrationGating:
    """Marker file behaviour and basic short-circuits."""

    def test_marker_present_is_a_no_op(self, tmp_path):
        fstab = _write(tmp_path / "fstab", "UUID=1 /media/x ext4 defaults 0 2\n")
        fstab_yaml = tmp_path / "fstab.yaml"
        marker = tmp_path / ".fstab-migrated"
        marker.touch()

        result = migrate_etc_fstab(
            fstab_path=fstab,
            controller_yaml_path=tmp_path / "controller.yaml",
            fstab_yaml_path=fstab_yaml,
            marker_path=marker,
            backup_path=tmp_path / "backup",
        )
        assert result == {"migrated": False, "reason": "already-migrated", "count": 0}
        # /etc/fstab untouched, fstab.yaml not written.
        assert "UUID=1 /media/x" in fstab.read_text()
        assert not fstab_yaml.exists()

    def test_no_sources_writes_marker_only(self, tmp_path):
        marker = tmp_path / ".fstab-migrated"
        result = migrate_etc_fstab(
            fstab_path=tmp_path / "nonexistent-fstab",
            controller_yaml_path=tmp_path / "missing.yaml",
            fstab_yaml_path=tmp_path / "fstab.yaml",
            marker_path=marker,
            backup_path=tmp_path / "backup",
        )
        assert result["migrated"] is True
        assert result["count"] == 0
        assert marker.exists()

    def test_idempotent_when_called_twice(self, tmp_path):
        _write(tmp_path / "fstab",
               "UUID=1 /media/wrolpi/usb ext4 defaults 0 2\n")
        fstab_yaml_p = tmp_path / "fstab.yaml"
        marker = tmp_path / ".fstab-migrated"

        first = migrate_etc_fstab(
            fstab_path=tmp_path / "fstab",
            controller_yaml_path=tmp_path / "controller.yaml",
            fstab_yaml_path=fstab_yaml_p,
            marker_path=marker,
            backup_path=tmp_path / "backup",
        )
        assert first["migrated"] is True

        # Manually re-add an entry to simulate a stray write between runs.
        # The marker should still short-circuit and leave fstab.yaml alone.
        before = fstab_yaml_p.read_text()
        second = migrate_etc_fstab(
            fstab_path=tmp_path / "fstab",
            controller_yaml_path=tmp_path / "controller.yaml",
            fstab_yaml_path=fstab_yaml_p,
            marker_path=marker,
            backup_path=tmp_path / "backup",
        )
        assert second["migrated"] is False
        assert second["reason"] == "already-migrated"
        assert fstab_yaml_p.read_text() == before


class TestEtcFstabMigration:

    def test_only_primary_entry_is_left_alone(self, tmp_path):
        fstab = _write(tmp_path / "fstab", (
            "UUID=root / ext4 defaults 0 1\n"
            "UUID=primary /media/wrolpi ext4 defaults,nofail 0 2\n"
        ))
        fstab_yaml_p = tmp_path / "fstab.yaml"
        result = migrate_etc_fstab(
            fstab_path=fstab,
            controller_yaml_path=tmp_path / "controller.yaml",
            fstab_yaml_path=fstab_yaml_p,
            marker_path=tmp_path / "marker",
            backup_path=tmp_path / "backup",
        )
        assert result == {"migrated": True, "count": 0}
        # Primary still in fstab, intact.
        assert "UUID=primary /media/wrolpi ext4" in fstab.read_text()
        # fstab.yaml not written when no candidates.
        assert not fstab_yaml_p.exists()

    def test_secondary_entry_is_migrated(self, tmp_path):
        fstab = _write(tmp_path / "fstab", (
            "UUID=root / ext4 defaults 0 1\n"
            "UUID=primary /media/wrolpi ext4 defaults 0 2\n"
            "# WROLPi managed mount - added 2025-01-01T00:00:00\n"
            "UUID=secondary /media/wrolpi/2TB ext4 defaults,nofail 0 2\n"
        ))
        fstab_yaml_p = tmp_path / "fstab.yaml"
        result = migrate_etc_fstab(
            fstab_path=fstab,
            controller_yaml_path=tmp_path / "controller.yaml",
            fstab_yaml_path=fstab_yaml_p,
            marker_path=tmp_path / "marker",
            backup_path=tmp_path / "backup",
        )
        assert result["count"] == 1
        data = load_fstab_yaml(fstab_yaml_p)
        assert len(data.mounts) == 1
        e = data.mounts[0]
        assert e.device == "UUID=secondary"
        assert e.mount_point == "/media/wrolpi/2TB"
        assert e.fstype == "ext4"

        new_fstab = fstab.read_text()
        active_lines = [
            ln.strip() for ln in new_fstab.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        # Migrated line no longer active.
        assert not any("/media/wrolpi/2TB" in ln for ln in active_lines)
        # Commented form preserved.
        assert "migrated to fstab.yaml" in new_fstab

    def test_dedup_against_existing_fstab_yaml(self, tmp_path):
        from controller.lib.fstab_yaml import FstabEntry, FstabFile, save
        save(FstabFile(mounts=[
            FstabEntry("UUID=secondary", "/media/wrolpi/2TB", "ext4", "defaults"),
        ]), tmp_path / "fstab.yaml")

        fstab = _write(tmp_path / "fstab", (
            "UUID=primary /media/wrolpi ext4 defaults 0 2\n"
            "UUID=secondary /media/wrolpi/2TB ext4 defaults 0 2\n"
        ))
        result = migrate_etc_fstab(
            fstab_path=fstab,
            controller_yaml_path=tmp_path / "controller.yaml",
            fstab_yaml_path=tmp_path / "fstab.yaml",
            marker_path=tmp_path / "marker",
            backup_path=tmp_path / "backup",
        )
        # Same mount point already in fstab.yaml; no new entry but /etc/fstab
        # line is still commented out (cleanup).
        assert result["count"] == 0
        data = load_fstab_yaml(tmp_path / "fstab.yaml")
        assert len(data.mounts) == 1
        assert "migrated to fstab.yaml" in fstab.read_text()

    def test_non_media_entries_untouched(self, tmp_path):
        fstab = _write(tmp_path / "fstab", (
            "UUID=root / ext4 defaults 0 1\n"
            "UUID=home /home ext4 defaults 0 2\n"
            "tmpfs /tmp tmpfs defaults 0 0\n"
        ))
        migrate_etc_fstab(
            fstab_path=fstab,
            controller_yaml_path=tmp_path / "controller.yaml",
            fstab_yaml_path=tmp_path / "fstab.yaml",
            marker_path=tmp_path / "marker",
            backup_path=tmp_path / "backup",
        )
        new_fstab = fstab.read_text()
        for ln in ("UUID=root / ext4", "UUID=home /home ext4", "tmpfs /tmp"):
            assert ln in new_fstab
            assert f"migrated to fstab.yaml: {ln}" not in new_fstab

    def test_excluded_mount_points_skipped(self, tmp_path):
        fstab = _write(
            tmp_path / "fstab",
            "UUID=temp /media/wrolpi_temp_onboarding ext4 defaults 0 2\n")
        result = migrate_etc_fstab(
            fstab_path=fstab,
            controller_yaml_path=tmp_path / "controller.yaml",
            fstab_yaml_path=tmp_path / "fstab.yaml",
            marker_path=tmp_path / "marker",
            backup_path=tmp_path / "backup",
        )
        assert result["count"] == 0
        # /etc/fstab not commented out — never claimed.
        assert "/media/wrolpi_temp_onboarding" in fstab.read_text()

    def test_backup_written_when_changes_made(self, tmp_path):
        fstab_content = "UUID=secondary /media/wrolpi/2TB ext4 defaults 0 2\n"
        fstab = _write(tmp_path / "fstab", fstab_content)
        backup = tmp_path / "backup"

        migrate_etc_fstab(
            fstab_path=fstab,
            controller_yaml_path=tmp_path / "controller.yaml",
            fstab_yaml_path=tmp_path / "fstab.yaml",
            marker_path=tmp_path / "marker",
            backup_path=backup,
        )
        assert backup.exists()
        assert backup.read_text() == fstab_content


class TestControllerYamlMigration:
    """drives.mounts in controller.yaml gets lifted into fstab.yaml and
    the key is stripped from the controller.yaml file."""

    def test_drives_mounts_migrated_to_fstab_yaml(self, tmp_path):
        controller_yaml = _write_yaml(tmp_path / "controller.yaml", {
            "port": 80,
            "drives": {
                "mounts": [{
                    "device": "UUID=secondary",
                    "mount_point": "/media/wrolpi/2TB",
                    "fstype": "ext4",
                    "options": "defaults",
                }],
            },
        })
        fstab_yaml_p = tmp_path / "fstab.yaml"
        result = migrate_etc_fstab(
            fstab_path=tmp_path / "nonexistent-fstab",
            controller_yaml_path=controller_yaml,
            fstab_yaml_path=fstab_yaml_p,
            marker_path=tmp_path / "marker",
            backup_path=tmp_path / "backup",
        )
        assert result["count"] == 1
        data = load_fstab_yaml(fstab_yaml_p)
        assert data.mount_points() == {"/media/wrolpi/2TB"}

        # drives.mounts stripped, other keys preserved.
        post = yaml.safe_load(controller_yaml.read_text())
        assert post.get("port") == 80
        assert "mounts" not in (post.get("drives") or {})

    def test_drives_mounts_with_excluded_paths(self, tmp_path):
        # The reserved mount points should not be migrated; they should
        # remain in drives.mounts? — actually no, drives.mounts is being
        # retired entirely.  We migrate all valid candidates and drop the
        # key regardless.  Reserved entries are silently filtered out.
        controller_yaml = _write_yaml(tmp_path / "controller.yaml", {
            "drives": {
                "mounts": [
                    {"device": "UUID=primary",
                     "mount_point": "/media/wrolpi",
                     "fstype": "ext4",
                     "options": "defaults"},
                    {"device": "UUID=secondary",
                     "mount_point": "/media/wrolpi/2TB",
                     "fstype": "ext4",
                     "options": "defaults"},
                ],
            },
        })
        fstab_yaml_p = tmp_path / "fstab.yaml"
        result = migrate_etc_fstab(
            fstab_path=tmp_path / "nonexistent-fstab",
            controller_yaml_path=controller_yaml,
            fstab_yaml_path=fstab_yaml_p,
            marker_path=tmp_path / "marker",
            backup_path=tmp_path / "backup",
        )
        # Only the secondary made it across.
        assert result["count"] == 1
        data = load_fstab_yaml(fstab_yaml_p)
        assert data.mount_points() == {"/media/wrolpi/2TB"}

    def test_no_drives_key_is_a_noop(self, tmp_path):
        controller_yaml = _write_yaml(tmp_path / "controller.yaml", {"port": 80})
        fstab_yaml_p = tmp_path / "fstab.yaml"
        result = migrate_etc_fstab(
            fstab_path=tmp_path / "nonexistent-fstab",
            controller_yaml_path=controller_yaml,
            fstab_yaml_path=fstab_yaml_p,
            marker_path=tmp_path / "marker",
            backup_path=tmp_path / "backup",
        )
        assert result["count"] == 0
        # controller.yaml untouched.
        assert yaml.safe_load(controller_yaml.read_text()) == {"port": 80}


class TestCombinedSources:
    """Both /etc/fstab AND drives.mounts contain entries — merge dedup."""

    def test_merges_both_sources_dedup_by_mount_point(self, tmp_path):
        fstab = _write(tmp_path / "fstab",
                       "UUID=a /media/wrolpi/a ext4 defaults 0 2\n"
                       "UUID=both /media/wrolpi/both ext4 defaults 0 2\n")
        controller_yaml = _write_yaml(tmp_path / "controller.yaml", {
            "drives": {
                "mounts": [
                    {"device": "UUID=both",
                     "mount_point": "/media/wrolpi/both",
                     "fstype": "ext4",
                     "options": "defaults"},
                    {"device": "UUID=b",
                     "mount_point": "/media/wrolpi/b",
                     "fstype": "ext4",
                     "options": "defaults"},
                ],
            },
        })
        fstab_yaml_p = tmp_path / "fstab.yaml"
        result = migrate_etc_fstab(
            fstab_path=fstab,
            controller_yaml_path=controller_yaml,
            fstab_yaml_path=fstab_yaml_p,
            marker_path=tmp_path / "marker",
            backup_path=tmp_path / "backup",
        )
        # a (fstab only), both (both sources, dedup), b (controller only)
        assert result["count"] == 3
        data = load_fstab_yaml(fstab_yaml_p)
        assert data.mount_points() == {
            "/media/wrolpi/a", "/media/wrolpi/both", "/media/wrolpi/b",
        }
