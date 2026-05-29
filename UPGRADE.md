# Upgrading WROLPi

# Table of Contents

* [Upgrading Docker containers](#upgrading-docker-containers)
* [Upgrading Raspberry Pi or Debian 12 Installation](#upgrading-raspberry-pi-or-debian-12-installation)
* [Upgrading a WROLPi Portable USB](#upgrading-a-wrolpi-portable-usb)

## Upgrading Docker containers

1. Stop docker containers
    * `docker-compose stop`
2. Pull the latest master
    * `git pull origin master --ff`
3. Build all docker containers
    * `docker-compose build --parallel`
4. Create the map volumes
    * `docker volume create --name=openstreetmap-data`
    * `docker volume create --name=openstreetmap-rendered-tiles`
5. Turn on the database
    * `docker-compose up -d db`
6. Upgrade the database
    * `docker-compose run --rm api db upgrade`
7. Start all docker containers
    * `docker-compose up -d`

## Upgrading Raspberry Pi or Debian 12 Installation

1. Run the upgrade script
    * `sudo /bin/bash /opt/wrolpi/upgrade.sh`
    * (If the upgrade script does not exist, run the installation script:  `sudo /bin/bash /opt/wrolpi/install.sh`)

## Upgrading a WROLPi Portable USB

A [WROLPi Portable](INSTALL.md#wrolpi-portable-live-usb) USB carries two
partitions: the ISO (boot) partition and a `persistence` partition — created on
the first boot — that holds your library, database, and configuration.  To move
to a newer ISO without losing the persistence partition, use the
`scripts/wrolpi-usb.sh` tool from any Linux host (your own computer, or the
WROLPi USB itself booted on another machine).

1. Download the new `WROLPi-v*-amd64.iso` from [wrolpi.org](https://wrolpi.org).
2. Plug the WROLPi USB into a Linux host and identify its device node (e.g. `/dev/sdb`) with `lsblk`.
3. Run the upgrade:
    * `sudo ./scripts/wrolpi-usb.sh upgrade WROLPi-v<version>-amd64.iso /dev/sdX`
4. Eject the USB and boot it to verify.

The tool backs up the current partition table to `/tmp/` first, overwrites only
the ISO partition, and re-adds the `persistence` partition entry at its original
location.  The ISO partition reserves 8 GiB of headroom so a larger future ISO
still fits ahead of the persistence partition.

### Converting an existing data drive is not supported

There is no in-place conversion of a drive that already holds your data into a
WROLPi Portable USB — flashing the ISO erases the whole drive.  To turn a drive
you already use into a WROLPi USB without losing your files:

1. Back up everything on the drive to another disk.
2. Flash the whole drive with the ISO (`dd`/Etcher/Rufus — this erases it).
3. Boot once so WROLPi creates its persistence partition and sets itself up.
4. Copy your data into `/media/wrolpi/`, then let WROLPi refresh/repair to index the restored files.

Afterwards, future ISO upgrades preserve your library via the `upgrade` command above.
