"""
Tests for controller.lib.fstab_yaml — the on-drive fstab.yaml reader/writer.

All tests use real files in tmp_path; no mocks anywhere.  The file format is
a stable on-disk contract so the round-trip tests are the load-bearing ones.
"""

import yaml

from controller.lib.fstab_yaml import (
    FstabEntry,
    FstabFile,
    SCHEMA_VERSION,
    load,
    save,
)


class TestFstabEntry:

    def test_to_dict_round_trip(self):
        entry = FstabEntry("UUID=abc", "/media/x", "ext4", "defaults,noatime")
        d = entry.to_dict()
        assert d == {
            "device": "UUID=abc",
            "mount_point": "/media/x",
            "fstype": "ext4",
            "options": "defaults,noatime",
        }
        assert FstabEntry.from_dict(d) == entry

    def test_from_dict_supplies_defaults(self):
        entry = FstabEntry.from_dict({"device": "UUID=abc", "mount_point": "/media/x"})
        assert entry.fstype == "auto"
        assert entry.options == "defaults"

    def test_empty_options_falls_back_to_defaults(self):
        # Migration data sometimes has options=None; treat as "defaults".
        entry = FstabEntry.from_dict({
            "device": "UUID=abc",
            "mount_point": "/media/x",
            "fstype": "ext4",
            "options": None,
        })
        assert entry.options == "defaults"


class TestFstabFile:

    def test_mount_points(self):
        f = FstabFile(mounts=[
            FstabEntry("UUID=1", "/media/a", "ext4"),
            FstabEntry("UUID=2", "/media/b", "ext4"),
        ])
        assert f.mount_points() == {"/media/a", "/media/b"}

    def test_find_by_mount_point(self):
        e = FstabEntry("UUID=1", "/media/a", "ext4")
        f = FstabFile(mounts=[e])
        assert f.find_by_mount_point("/media/a") is e
        assert f.find_by_mount_point("/media/missing") is None

    def test_add_or_replace_same_mount_point(self):
        f = FstabFile(mounts=[FstabEntry("UUID=1", "/media/a", "ext4", "defaults")])
        f.add_or_replace(FstabEntry("UUID=1", "/media/a", "ext4", "noatime"))
        assert len(f.mounts) == 1
        assert f.mounts[0].options == "noatime"

    def test_add_or_replace_same_device_different_mount_point(self):
        # User remounts the same drive to a new directory; old row should
        # drop, not accumulate.
        f = FstabFile(mounts=[FstabEntry("UUID=1", "/media/old", "ext4")])
        f.add_or_replace(FstabEntry("UUID=1", "/media/new", "ext4"))
        assert len(f.mounts) == 1
        assert f.mounts[0].mount_point == "/media/new"

    def test_add_or_replace_preserves_unrelated(self):
        f = FstabFile(mounts=[
            FstabEntry("UUID=1", "/media/a", "ext4"),
            FstabEntry("UUID=2", "/media/b", "ext4"),
        ])
        f.add_or_replace(FstabEntry("UUID=3", "/media/c", "ext4"))
        assert {m.mount_point for m in f.mounts} == {"/media/a", "/media/b", "/media/c"}

    def test_remove_by_mount_point_returns_true_when_removed(self):
        f = FstabFile(mounts=[FstabEntry("UUID=1", "/media/a", "ext4")])
        assert f.remove_by_mount_point("/media/a") is True
        assert f.mounts == []

    def test_remove_by_mount_point_returns_false_when_absent(self):
        f = FstabFile()
        assert f.remove_by_mount_point("/media/a") is False


class TestLoadSave:

    def test_load_missing_file_is_empty(self, tmp_path):
        f = load(tmp_path / "missing.yaml")
        assert f.version == SCHEMA_VERSION
        assert f.mounts == []

    def test_load_empty_file_is_empty(self, tmp_path):
        p = tmp_path / "fstab.yaml"
        p.write_text("")
        f = load(p)
        assert f.mounts == []

    def test_load_malformed_yaml_is_empty(self, tmp_path):
        p = tmp_path / "fstab.yaml"
        p.write_text("this: is: not: valid: yaml: [")
        f = load(p)
        assert f.mounts == []

    def test_load_skips_unrecognised_fields(self, tmp_path):
        # Forward-compat: future entries may carry extra fields; load should
        # silently ignore them.
        p = tmp_path / "fstab.yaml"
        p.write_text(yaml.safe_dump({
            "version": 1,
            "mounts": [{
                "device": "UUID=1",
                "mount_point": "/media/a",
                "fstype": "ext4",
                "options": "defaults",
                "future_field": "ignored",
            }],
        }))
        f = load(p)
        assert len(f.mounts) == 1

    def test_save_creates_parent_directory(self, tmp_path):
        nested = tmp_path / "config" / "fstab.yaml"
        save(FstabFile(mounts=[FstabEntry("UUID=1", "/media/a", "ext4")]), nested)
        assert nested.exists()

    def test_save_is_atomic(self, tmp_path):
        # We can't directly observe atomicity in a unit test, but we can
        # confirm the temp file is gone after a successful write.
        p = tmp_path / "fstab.yaml"
        save(FstabFile(mounts=[FstabEntry("UUID=1", "/media/a", "ext4")]), p)
        assert p.exists()
        assert not (tmp_path / "fstab.yaml.tmp").exists()

    def test_round_trip(self, tmp_path):
        original = FstabFile(mounts=[
            FstabEntry("UUID=1", "/media/b", "ext4", "defaults"),
            FstabEntry("UUID=2", "/media/a", "exfat", "defaults,uid=1001"),
        ])
        p = tmp_path / "fstab.yaml"
        save(original, p)
        loaded = load(p)
        # Mount points sorted on save:
        assert [m.mount_point for m in loaded.mounts] == ["/media/a", "/media/b"]
        # Other fields preserved:
        a = loaded.find_by_mount_point("/media/a")
        assert a.device == "UUID=2"
        assert a.fstype == "exfat"
        assert a.options == "defaults,uid=1001"

    def test_save_sorts_mounts(self, tmp_path):
        p = tmp_path / "fstab.yaml"
        save(FstabFile(mounts=[
            FstabEntry("UUID=2", "/media/zeta", "ext4"),
            FstabEntry("UUID=1", "/media/alpha", "ext4"),
        ]), p)
        raw = yaml.safe_load(p.read_text())
        assert [m["mount_point"] for m in raw["mounts"]] == ["/media/alpha", "/media/zeta"]
