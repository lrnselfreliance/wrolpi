# Mount Issues — 2026-07-05 Support Session

Problems found while onboarding a user's new Debian WROLPi (amd64 mini PC, hostname
`matrix-Q5mini`) with a 4TB NTFS USB drive ("UGREEN 4TB", `/dev/sdb2`) containing the
backup of their previous WROLPi. This document records each problem, its root cause,
the fix, and a test plan for verifying the changes.

Fixes shipped on `master`: `c25902b9`, `2e660cdb`. The user's box currently tracks
**master**; it should be switched back to `release` after the next release is cut
(`sudo /opt/wrolpi/upgrade.sh -b release`).

(The same session also produced upgrade-pipeline fixes on `release` —
`e8c6d841` cert SAN name constraints, `e6ace594` checkout ambiguity, `02eb8d70` gpg
`--batch --yes`, `eefebe17` non-interactive apt + `dpkg --configure -a`,
`7bf7d9aa` postgres healing in `reset_api_db.sh`, `da35d39d` portable-path postgres
ownership guard. Those are separate from the mount work but the same box exercised
them all.)

---

## Architecture primer (required to understand the bugs)

WROLPi has **two separate persistence stores** for mounts:

| Store | Owner | Applied by | Used for |
|---|---|---|---|
| `/etc/fstab` | host system (`controller/lib/fstab.py`) | systemd at boot | the **primary** mount (`/media/wrolpi`) |
| `fstab.yaml` (`/media/wrolpi/config/fstab.yaml`) | WROLPi (`controller/lib/fstab_yaml.py`) | `wrolpi-mounts.service` reconciler | **secondary** drives under `/media/*` |

The reconciler (`controller/lib/reconciler.py`) hard-refuses to manage
`RESERVED_MOUNT_POINTS = {"/media/wrolpi", "/media/wrolpi_temp_onboarding"}` — the
primary mount must be live *before* the reconciler can even read fstab.yaml (which
lives on the primary drive). The onboarding flow (`controller/lib/onboarding.py`)
already respected this split; the Disks page did not (Problem 2).

---

## Problem 1: "Existing Files Detected" dialog blocked the mount

**Symptom:** Mounting `sdb2` at `/media/wrolpi` showed a warning: *Found `tags`
(271 B) at the mount target… Mounting now would hide them.*

**Not a bug.** This is `check_shadowed_data()` working as designed — it protects
users who downloaded gigabytes onto the SD card / root disk before mounting a drive.
Here it guarded a 271-byte stub created while the box ran drive-less. "Mount Anyway"
(`force_shadowed`) is the correct answer when the shadowed data is disposable.

## Problem 2: "Mount Anyway" could never mount the primary drive

**Symptom:** After forcing past the shadow dialog, the mount failed; the
wrolpi-mounts journal later showed `Reconcile complete: 0 mounted …` and (after
better logging) `1 desired, 1 skipped — Skipped /media/wrolpi: reserved mount point`.

**Root cause (design bug):** `POST /disks/mount` wrote *every* mount into
`fstab.yaml` and delegated to the reconciler — which skips `/media/wrolpi` as
reserved. Mounting the primary drive from the Disks page was therefore structurally
impossible, on every WROLPi, and each attempt left a **phantom fstab.yaml entry**
behind.

**Fix (`2e660cdb`):** `disk_mount` detects `mount_point == get_media_directory()`
and takes the onboarding path instead: `mount_drive()` directly, persist via
`/etc/fstab` (`add_etc_fstab_entry`), and delete any phantom fstab.yaml entry.
The reconciler is not involved.

## Problem 3: NTFS dirty flag refused the mount

**Symptom:** Even a manual `mount` of the NTFS volume failed until
`sudo ntfsfix -d /dev/sdb2` was run ("Mounting volume… OK, processed successfully").

**Root cause:** NTFS volumes touched by Windows Fast Startup, hibernation, or an
unclean unplug carry a dirty flag; ntfs-3g refuses to mount them. Extremely common
on store-bought / Windows-formatted USB drives.

**Fix (`c25902b9`):** `mount_drive()` (`controller/lib/disks.py`) now runs
`ntfsfix -d <device>` before mounting `ntfs`/`ntfs3` volumes. Non-fatal (a failed
ntfsfix logs a warning and the mount still reports the real error); a no-op on
clean volumes. Note: this covers UI-initiated mounts. A *boot-time* mount of a
dirty NTFS primary via /etc/fstab will still fail until the user mounts once via
the UI — `nofail` keeps the boot alive.

## Problem 4: UI mount protection was wrong in both directions

**Symptom (a):** the mounted `/media/wrolpi` row showed "System" with **no Persist
toggle** — a manually mounted primary drive could not be persisted from the UI.
**Symptom (b):** `sda1` (vfat, mounted at `/boot/efi`) showed a red **Unmount**
button and a Persist toggle — one misclick from unmounting the EFI partition.

**Root cause:** both UIs used a fixed list
`PROTECTED_MOUNTS = ['/', '/boot', '/boot/firmware', '/media/wrolpi']`. It
over-protected the primary mount (Persist is safe and necessary) and
under-protected everything not in the list (`/boot/efi`, swap, any other system
mount).

**Fix (`c25902b9`):** classification is now rule-based in both UIs
(`app/src/components/admin/ControllerPage.js` and
`controller/templates/index.html` — keep parity):
- `isPrimary` (`/media/wrolpi`): Persist toggle **enabled**, Unmount **blocked** ("System").
- `isSystemMount` (mounted anywhere outside `/media/`): fully untouchable.
- other `/media/*` mounts: unchanged (Persist toggle + Unmount).

Backing API (`controller/api/disks.py`): `POST/DELETE /disks/fstab` for the primary
mount route to `/etc/fstab` instead of fstab.yaml; `GET /disks/fstab` includes the
primary's `/etc/fstab` entry so the toggle reflects reality.

## Problem 5: Phantom fstab.yaml entries misreported persistence

**Symptom:** after Problem 2 left `/media/wrolpi` in fstab.yaml, the fstab list
endpoint reported it, so the Persist toggle would show "Enabled" while the drive
would in fact **not** mount at boot.

**Fix (`2e660cdb`):** entries for `RESERVED_MOUNT_POINTS` in fstab.yaml are hidden
from `GET /disks/fstab`, and are actively deleted whenever the primary mount is
mounted (`POST /disks/mount`), persisted (`POST /disks/fstab`), or un-persisted
(`DELETE /disks/fstab` — which succeeds if *either* store had an entry).

## Problem 6: wrolpi-mounts logs couldn't explain "did nothing"

**Symptom:** journal showed only `Reconcile complete: 0 mounted, 0 unmounted, 0
mount failures, 0 unmount failures` — indistinguishable between "nothing
configured", "everything already mounted", and "everything skipped".

**Fix (`c25902b9`):** `ReconcileResult` gained `desired_count` and
`already_mounted`; `mount_runner.py` now logs
`N desired, N already mounted, N skipped, …`, one line per already-mounted mount,
one line per skipped entry **with the reason**, and an explicit
"`fstab.yaml lists no mounts; nothing to reconcile.`" when empty. This logging
diagnosed Problem 2 within one screenshot.

## Problem 7 (adjacent): `/etc/fstab` entries missed uid/gid for NTFS

`add_fstab_entry()` only added `uid=/gid=` mount options for `exfat`/`vfat`;
`mount_drive()` already covered `ntfs`/`ntfs3` too. Without them, a boot-mounted
NTFS drive is root-owned (functional but inconsistent). Fixed in `c25902b9` to
match `mount_drive()`.

## Problem 8: Postgres died after reboot — bootstrap bind-mounts on an installed box

**Symptom:** after the reboot that mounted the NTFS drive via `/etc/fstab`, the API
got `connection to server at "127.0.0.1", port 5432 failed: Connection refused`.
`systemctl`/help.sh showed postgres "running" (the umbrella `postgresql.service`
unit is active even with zero clusters). `sudo pg_lsclusters` printed **no clusters
at all**, and `findmnt /var/lib/postgresql` showed
`/dev/sdb2[/config/postgresql/data] fuseblk` — the smoking gun.

**Root cause:** the box was installed from the WROLPi Portable live USB, whose
`wrolpi-bootstrap.service` runs at every boot and bind-mounted
`/media/wrolpi/config/postgresql/{data,config}` over `/var/lib/postgresql` and
`/etc/postgresql` **unconditionally** — a design meant for live boots (ephemeral
squashfs root; postgres must live on the persistence partition) that leaked into
the installed case. Consequences on this box:

- Drive-less (morning): the cluster silently lived on the root disk *under
  `/media/wrolpi/config`* — which is why `repair.sh`'s recursive
  `chown -R wrolpi:wrolpi /media/wrolpi/config` broke backend startup
  (`pg_filenode.map: Permission denied`). **This resolves the "root cause
  unknown" from the earlier postgres incident.**
- Drive mounted (evening): the binds pointed postgres into the NTFS drive, and a
  postgres data directory cannot exist on NTFS (no POSIX ownership / 0700), so
  the cluster effectively vanished.

**Fix:** `wrolpi-bootstrap.sh` now applies the postgres directory-prep and
bind-mounts **only when `MODE != installed`** (live boots). Installed systems keep
postgres at the normal Debian root-filesystem paths. If an installed box still has
a stale bind active from an old boot, the script logs a NOTE to reboot rather than
touching it. On the first boot with the fix, an installed box with no root-disk
cluster gets one created and initialized automatically by the bootstrap's existing
`pg_createcluster`/`initialize_api_db.sh` logic; the DB content rebuilds from the
drive's configs plus a file refresh (configs are the source of truth). The old
cluster files remain as dead weight under `/media/wrolpi/config/postgresql`
(root disk, shadowed by the mount) — deliberately not auto-deleted.

**Design decision (2026-07-06, Roland):** portable is detected by the presence of
a live boot medium (`MODE` in wrolpi-bootstrap.sh — checked fresh every boot);
only then does Postgres live on the media directory via bind-mounts. Installed
systems always use the root filesystem. No cluster-migration code for existing
portable-installed boxes with ext4 drives: no users are on the portable version
yet, so an abandoned drive-side cluster (rebuilt from configs + file refresh) is
acceptable. repair.sh's ownership restore keys off the *active bind*
(`mountpoint -q /var/lib/postgresql`), not directory existence.

**Related discovery:** nothing ever updated `/usr/local/sbin/wrolpi-bootstrap.sh`
on installed boxes — it was frozen at image-build time, so bootstrap fixes could
never ship. `repair.sh` now copies the script (and its unit) from the repo when
present (`9d778d25`).

**Recovery for this box:** `sudo /opt/wrolpi/upgrade.sh` (its repair step installs
the fixed bootstrap) → reboot → bootstrap creates the root-disk cluster and
initializes the DB → Files refresh.

## Problem 9: a down database blocked the upgrade that carried its fix

**Symptom:** re-running the upgrade to deliver the Problem 8 fix failed at
`main.py db upgrade` with the same `Connection refused` — `scripts/upgrade.sh`
ran the migration under `set -e` *before* `repair.sh`, and `repair.sh` itself ran
`initialize_api_db.sh` / the superuser `psql` fatally too.

**Fix (`756c063d`):** the migration and the Postgres configuration steps warn and
continue instead of aborting. The migration is retried by
`initialize_api_db.sh` during repair; if the database is still down afterwards
the API reports it loudly, while the system-level work (configs, services,
bootstrap refresh) always completes — which is exactly what delivers DB fixes.

---

## State of the user's box (for later reference)

- Drive: `/dev/sdb2`, NTFS, label "UGREEN 4TB", `UUID=A652E6C452E9877` (verify on
  box — read from a photo), GPT with a Microsoft-reserved `sdb1`.
- Dirty flag cleared manually with `ntfsfix -d`; mounted manually, then persisted
  via the fixed UI (writes UUID-keyed `/etc/fstab` entry with
  `defaults,nofail,x-systemd.device-timeout=10s,uid=…,gid=…`).
- If the user earlier ran the suggested manual `tee -a /etc/fstab` line, the UI
  persist replaced it (`add_fstab_entry` dedups by mount point and device) — but
  verifying `/etc/fstab` has exactly **one** `/media/wrolpi` line is worth doing.
- Their old library configs live on the drive; configs import on API startup and a
  full **Files → Refresh** indexes the library.

---

## Test plan

### Already covered by automated tests

- `controller/test/test_disks.py`: ntfsfix runs before ntfs mounts; ntfsfix failure
  doesn't block the mount; ext4 never runs ntfsfix; uid/gid injection by fstype.
- `controller/test/test_fstab.py`: ntfs `/etc/fstab` entries get uid/gid.
- `controller/test/test_disks_api.py` (`TestPrimaryMountPersist`): primary
  POST/DELETE `/disks/fstab` route to `/etc/fstab`; failure propagation; list
  merges the primary `/etc/fstab` entry and hides phantoms; `POST /disks/mount`
  for primary mounts directly + persists + cleans phantom, never touches the
  reconciler; DELETE succeeds on phantom-only state.
- `controller/test/test_reconciler.py`: `desired_count` / `already_mounted`
  diagnostics.

Run: `cd controller && source venv/bin/activate && python -m pytest -p no:cacheprovider --confcutdir=. test/ -v`

### Manual / E2E scenarios (real hardware or QA Pi)

Primary mount lifecycle:
1. Fresh box, empty ext4 USB drive → Disks page → Mount at `/media/wrolpi` →
   mounts immediately, `/etc/fstab` gains one UUID-keyed line, Persist shows
   Enabled, fstab.yaml does NOT contain `/media/wrolpi` → reboot → mounted.
2. Same with a **dirty NTFS** drive (unplug it from a Windows box without eject,
   or `mount && unplug`): Mount from UI must succeed (ntfsfix runs) — check
   `journalctl -u wrolpi-controller` for the ntfsfix warning path.
3. Persist toggle OFF → `/etc/fstab` line removed (backup `/etc/fstab.backup.*`
   created), reboot → not mounted, UI shows Mount button. Toggle back ON.
4. Shadow dialog: put a file at `/media/wrolpi` while unmounted → Mount → dialog
   appears → Cancel leaves everything untouched → Mount Anyway proceeds.
5. Phantom self-heal: hand-write a `/media/wrolpi` entry into
   `/media/wrolpi/config/fstab.yaml`… (note: file lives *on* the primary drive;
   craft while mounted) → restart wrolpi-mounts → journal says
   `Skipped /media/wrolpi: reserved mount point` → toggle Persist off/on →
   entry gone from fstab.yaml, journal clean on next restart.

Secondary drives (must be unchanged):
6. Mount a second USB drive at `/media/wrolpi/usb` → entry goes to fstab.yaml
   (NOT `/etc/fstab`), reconciler mounts it, journal shows `1 desired … 1 mounted`
   or `1 already mounted` on re-runs. Unmount removes it. Reboot persistence works.

UI classification (check BOTH UIs — React ControllerPage and the simplified
Controller page at :8086):
7. `/boot/efi`, `/`, swap rows: Action "System", Persist "-" — no buttons.
8. `/media/wrolpi` row when mounted: Persist toggle present, Action "System".
9. Unmounted partition rows: green Mount button.

Modes:
10. WROL mode enabled → Persist toggle and Mount return a clear 403 error.
11. Docker mode → Disks section reports unavailable (501), no crash.

Diagnostics:
12. `journalctl -u wrolpi-mounts -n 30` after any reconcile shows the new
    `N desired, N already mounted, N skipped …` line and per-entry reasons; with
    empty fstab.yaml shows "lists no mounts; nothing to reconcile."

Portable (live USB) postgres placement:
13. Boot the Portable ISO (direct/dd mode) → `findmnt /var/lib/postgresql` shows
    the bind onto the persistence partition; cluster online; data survives
    reboot. Run repair.sh during the live session → cluster still owned by
    postgres afterwards (the bind-keyed ownership restore).
14. Installed system (any) → `findmnt /var/lib/postgresql` prints nothing;
    `pg_lsclusters` shows the cluster at /var/lib/postgresql/15/main; a stale
    bind from an old bootstrap logs the "reboot to move Postgres" NOTE and is
    gone after reboot.

Regression:
15. Full onboarding flow on a wiped box (temp-mount probe → commit) still mounts,
    writes `/etc/fstab`, and starts repair — it shares `add_etc_fstab_entry` and
    `mount_drive` with the new Disks-page path.
16. `cypress` run against the QA Pi (`cd app && npm run cy:run`) for general UI
    regressions.
