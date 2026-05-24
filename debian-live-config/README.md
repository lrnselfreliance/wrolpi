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

## Implementation status

- [x] **Phase 1 — merged live + chroot config**:  Single `debian-live-config/`
      produces a Debian Live ISO with the full WROLPi stack, XFCE auto-login
      as `wrolpi`, persistence partition created on first boot.
- [ ] **Phase 2 — Calamares installer**:  Add `calamares` package and a
      desktop launcher so users can install WROLPi to disk.
- [ ] **Phase 3 — branding + release**:  WROLPi branding for Calamares,
      CI on tag, hosting, wrolpi.org docs.

## References

- Debian Live Manual: https://live-team.pages.debian.net/live-manual/html/live-manual/index.en.html
- Persistence: https://live-team.pages.debian.net/live-manual/html/live-manual/customizing-run-time-behaviours.en.html
