# Installing WROLPi

There are several ways to run WROLPi.  Pick the one that matches your hardware:

* [WROLPi Portable (Live USB)](#wrolpi-portable-live-usb) — boot a full WROLPi from a USB stick on any x86 PC or laptop, no installation required.
* [Debian 13 Install](#debian-13-install) — install WROLPi onto an x86 PC or laptop.
* [Raspberry Pi Install](#raspberry-pi-install) — install WROLPi onto a Raspberry Pi with an external drive.

After installing, follow [First Boot](#first-boot) to set up your drive.
* [Docker](docker/README.md) — run the WROLPi containers on an existing Linux host (best for trying it out or development).

See [UPGRADE.md](UPGRADE.md) for upgrading an existing WROLPi.

## WROLPi Portable (Live USB)

WROLPi Portable is a bootable amd64 image that runs a complete WROLPi system
directly off a USB drive on any x86 PC or laptop — nothing is installed to the
computer's internal disk.  On the first boot it creates a `persistence`
partition on the USB drive so your library, database, and configuration survive
reboots.

You will need:

* A USB drive of at least 16 GB (32 GB+ recommended so there is room for your library).
* An x86 PC or laptop that can boot from USB.

Steps:

1. Download the latest `WROLPi-v*-amd64.iso` from [wrolpi.org](https://wrolpi.org).
2. Flash the whole drive with the ISO using Raspberry Pi Imager, Rufus, or `dd`:
   ```
   sudo dd if=WROLPi-v<version>-amd64.iso of=/dev/sdX bs=4M status=progress conv=fsync
   ```
   (Replace `/dev/sdX` with your USB drive.  This erases the whole drive.)
3. Boot the PC from the USB drive.  At the boot menu, choose **Run WROLPi (live)**.
4. The first boot sets WROLPi up automatically: it creates the persistence
   partition, initializes the database, and starts the services.  This takes a
   minute or two; progress is shown on screen.
5. Once the desktop loads, browse to https://wrolpi.local or the IP address of
   your WROLPi.  Wi-Fi hotspot and all other features work as usual.

Notes:

* **Installing to internal disk.**  The same boot menu offers **Install** /
  **Graphical Install** entries that run the standard Debian Installer if you
  would rather install WROLPi onto the computer's internal disk instead of
  running from the USB.
* **Ventoy / multiboot USBs.**  Booting the ISO via Ventoy, YUMI, Easy2Boot, or
  any other tool that loop-mounts the ISO works, but runs **ephemerally** — the
  library lives in RAM and is lost on reboot, because WROLPi cannot safely write
  a persistence partition onto your multiboot stick.  A first-boot dialog warns
  you when this happens.  For persistent use, flash the ISO directly to its own
  drive as shown above.
* **Upgrading.**  See [Upgrading a WROLPi Portable USB](UPGRADE.md#upgrading-a-wrolpi-portable-usb)
  to move to a newer ISO without losing your library.

## Debian 13 Install

Install WROLPi onto the internal disk of an x86 PC or laptop.  This uses the same
`WROLPi-v*-amd64.iso` as WROLPi Portable.

1. Download the latest `WROLPi-v*-amd64.iso` from [wrolpi.org](https://wrolpi.org) and flash it to a USB drive
   (see [WROLPi Portable](#wrolpi-portable-live-usb) step 2).
2. Boot the PC from the USB drive.  At the boot menu, choose **Install** or **Graphical Install**.
3. Install Debian 13 as you would like.
    1. It is recommended to use the hostname **wrolpi**.
    2. WROLPi is installed along with Debian; there is nothing extra to select.
4. Unplug the USB drive after the installation has completed, and reboot.
5. Continue with [First Boot](#first-boot).

## Raspberry Pi Install

Install WROLPi onto a Raspberry Pi.  An external drive is recommended for your library.

1. Download the latest `WROLPi-v*-aarch64-desktop.img.xz` from [wrolpi.org](https://wrolpi.org).
2. Flash it to an SD card using Raspberry Pi Imager.
3. Plug in your external drive, insert the SD card, and boot the Raspberry Pi.
4. On the first boot, Raspberry Pi OS asks you to create your own user.
5. Continue with [First Boot](#first-boot).

## First Boot

These steps are the same for every install.

1. Join the WROLPi hotspot (network **WROLPi**, password **wrolpi hotspot**; it starts on every boot), or connect
   your WROLPi to your network, then browse to https://wrolpi.local (or the IP address of your WROLPi).
2. **Choose your drive.**
    * **Raspberry Pi and Debian:** until a drive is set up, you will see the **Controller** with a *Welcome to WROLPi*
      wizard (also at http://wrolpi.local).  Select the drive which will hold your library; WROLPi mounts it
      at `/media/wrolpi`, adds it to `/etc/fstab`, and runs the repair script for you.  If the drive already holds a
      WROLPi library (from another WROLPi, or a backup), its configuration is used.  No external drive?  Choose **Run
      repair without external drive** to keep your library on the internal disk or SD card.
    * **WROLPi Portable:** nothing to do; your library lives in the persistence partition on the USB drive.
3. **Trust the certificate.**  Your browser will warn about the HTTPS certificate because it was made by your WROLPi,
   not by a public authority.  Download https://wrolpi.local/ca.crt and trust it on each device you use; see
   *Help > Certificates* on your WROLPi for per-device instructions.
4. **Wait for the first refresh.**  WROLPi refreshes all your files when it first starts so it can find anything already
   on the drive.  Your library looks empty, and Download and Upload are disabled, until the refresh completes.
5. Start adding content: download a video channel, archive a web page, or add a Zim (Wikipedia) file.  The *Help* page
   on your WROLPi explains each module.

You do not need to edit `/etc/fstab` or run `repair.sh` by hand.  `sudo /opt/wrolpi/repair.sh` is still available if
your WROLPi ever needs repairing.
