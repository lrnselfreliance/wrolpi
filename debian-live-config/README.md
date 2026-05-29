# Debian Live Config

Build a bootable amd64 ISO that boots into a full WROLPi system on any x86
PC.  Users can run WROLPi directly off the USB (a persistence partition is
created on the first boot so the database and media directory survive
reboots) or install to disk via the Calamares launcher on the desktop.

The chroot-phase build is identical for both modes; the resulting squashfs
is what runs in live mode AND what Calamares copies onto the target disk.

See https://live-team.pages.debian.net/live-manual/html/live-manual/index.en.html

## Build

```
sudo ./build.sh                # build from 'release' branch
sudo ./build.sh -b master      # build from a specific branch
```

Requires Debian / Ubuntu with `live-build` installed.  The resulting ISO is
written to this directory as `WROLPi-v${VERSION}-amd64.iso`.

Flash with Etcher, Rufus, Raspberry Pi Imager, or:

```
sudo dd if=WROLPi-v${VERSION}-amd64.iso of=/dev/sdX bs=4M status=progress conv=fsync
```

## Upgrading an existing WROLPi USB

A WROLPi USB carries two partitions: the ISO (boot) partition and a
`persistence` partition created on first boot that holds your library,
database, and configuration.  To move to a newer ISO without losing the
persistence partition, use `scripts/wrolpi-usb.sh` from any Linux host:

```
sudo ./scripts/wrolpi-usb.sh upgrade WROLPi-v${VERSION}-amd64.iso /dev/sdX
```

It backs up the partition table, overwrites only the ISO partition, and
re-adds the persistence partition entry at its original location.  The
ISO partition reserves 8 GiB of headroom so a larger future ISO still
fits ahead of the persistence partition.

## Converting an existing data drive (not supported)

There is no in-place conversion of a drive that already holds your data
into a WROLPi USB — flashing the ISO erases the whole drive, and there
is no safe, filesystem-agnostic way to graft WROLPi onto a full drive.
`scripts/wrolpi-usb.sh install` only prints this procedure:

1. Back up everything on the drive to another disk.
2. Flash the whole drive with the ISO (`dd`/Etcher/Rufus — this erases it).
3. Boot once so WROLPi creates its persistence partition and sets itself up.
4. Copy your data into `/media/wrolpi/`, then let WROLPi refresh/repair to
   index the restored files.

Afterwards, future ISO upgrades preserve your library via the
`upgrade` command above.

## Layout on disk

The drive carries everything WROLPi needs.  Postgres data lives alongside
the user's library so a drive moved between hosts keeps its full state:

```
/media/wrolpi/
  videos/                                ← user-facing media
  archives/
  zims/
  map/
  tags/
  config/
    wrolpi.yaml
    controller.yaml
    fstab.yaml
    ssl/
    postgresql/
      data/                              ← bind-mounted to /var/lib/postgresql
      config/                            ← bind-mounted to /etc/postgresql
```

## Booting via Ventoy or other multiboot USBs

Booting WROLPi via Ventoy, YUMI, Easy2Boot, AIO Boot, GLIM, or any other
tool that loop-mounts the ISO **works**, but only in ephemeral mode.

When the live medium appears under `/dev/loop*`, `/dev/dm-*`, or
`/dev/mapper/*` (the kernel's tell-tale for a loop/device-mapper-backed
file rather than a real partition), `wrolpi-bootstrap.sh` refuses to
create a persistence partition.  The underlying disk in that case is the
user's Ventoy stick, not a blank target — appending a new ext4 partition
to it would risk corrupting the user's other ISOs and data.

Instead the script mounts a `tmpfs` at `/media/wrolpi` (sized to half of
RAM by default), and the rest of the boot is unchanged.  Postgres
bind-mounts and DB initialisation all succeed, just into RAM.  The user
sees a "Running ephemerally…" notice in the first-boot dialog.

Everything written to the WROLPi library — downloads, archives, video
metadata, the database — is lost on reboot.  This mode is intended for
trying WROLPi out without committing a USB stick; for any real use,
flash the ISO directly to its own drive with `dd` or Etcher.

Direct (dd/Etcher) boot is distinguished by the live medium living under
`/dev/sd*`, `/dev/nvme*`, or `/dev/mmcblk*`; this is the only shape
where `wrolpi-bootstrap.sh` will touch the partition table.

(Future work: integrate with Ventoy's native `persistence.dat` flow so
the user can opt into a persistent ephemeral-style image without
needing a dedicated drive.)

## Implementation status

- [x] **Phase 1 — merged live + chroot config**:  Single `debian-live-config/`
      produces a Debian Live ISO with the full WROLPi stack, XFCE auto-login
      as `wrolpi`, persistence partition created on first boot.
- [x] **Phase 2 — Debian Installer**:  Standard `debian-installer` bundled
      via `lb config --debian-installer live --debian-installer-gui true`.
      GRUB exposes "Live", "Install", and "Graphical Install" entries.
      Live boots into WROLPi; Install/Graphical Install copy the running
      squashfs onto the target disk via Debian's `live-installer` flow.
      (We previously tried Calamares-as-the-installer; the XFCE
      desktop-icon click path proved unreliable in the wrolpi auto-login
      session and the upstream d-i path is better-tested.)
- [x] **Phase 3 — Ventoy/multiboot safety**:  `wrolpi-bootstrap.sh`
      detects when it's been booted via a loop-mounted ISO (Ventoy and
      friends) and falls back to a tmpfs-backed `/media/wrolpi` instead
      of writing a new partition onto the user's multiboot stick.
- [ ] **Release**:  CI on tag, hosting, wrolpi.org docs.

## References

- Debian Live Manual: https://live-team.pages.debian.net/live-manual/html/live-manual/index.en.html
- Persistence: https://live-team.pages.debian.net/live-manual/html/live-manual/customizing-run-time-behaviours.en.html
