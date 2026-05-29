# Installing WROLPi

There are several ways to run WROLPi.  Pick the one that matches your hardware:

* [WROLPi Portable (Live USB)](#wrolpi-portable-live-usb) — boot a full WROLPi from a USB stick on any x86 PC or laptop, no installation required.
* [Debian 12 Install](#debian-12-install) — install WROLPi onto an x86 PC or laptop.
* [Raspberry Pi Install](#raspberry-pi-install) — install WROLPi onto a Raspberry Pi with an external drive.
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
2. Flash the whole drive with the ISO using Etcher, Rufus, Raspberry Pi Imager, or `dd`:
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

## Debian 12 Install

Steps necessary to initialize your WROLPi after installing the Debian image from wrolpi.org

1. Download and copy a pre-built Debian image from https://wrolpi.org onto a USB thumb-drive (USB 2 recommended).
2. Insert the thumb-drive into the laptop, boot to the thumb-drive.
    1. Select "Start Installer".
    2. Install Debian 12 as you would like.
        1. It is recommended to use the hostname **wrolpi**.
        2. (WROLPi will be installed during the installation without your intervention.)
3. Unplug the thumb-drive after the installation has completed.
4. Login as the user _you_ created during installation.
5. Initialize the WROLPi databases using the repair script: `/opt/wrolpi/repair.sh`
6. Reboot: `reboot`
7. Browse to https://wrolpi.local or the IP address of your WROLPi!

## Raspberry Pi Install

Steps necessary to initialize your WROLPi after installing the Raspberry Pi image from wrolpi.org

1. Download and copy a pre-built image from https://wrolpi.org onto an SD card.
2. Boot the Raspberry Pi, login with username pi and password wrolpi.
3. Modify fstab to mount your external drive to /media/wrolpi (modify this command to match your system).
    * `echo '/dev/sda1 /media/wrolpi auto defaults,nofail 0 0' | sudo tee -a /etc/fstab`
4. Initialize the WROLPi databases using the repair script: `sudo /opt/wrolpi/repair.sh`
5. Reboot `sudo reboot`
6. Join the Hotspot or browse to https://wrolpi.local or the IP address of your WROLPi!
