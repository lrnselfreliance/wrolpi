# WROLPi

[![Build Status](https://img.shields.io/circleci/build/github/lrnselfreliance/wrolpi/release?label=release%20build)](https://app.circleci.com/pipelines/github/lrnselfreliance/wrolpi?branch=release&filter=all)
[![License: GPL v3](https://img.shields.io/github/license/lrnselfreliance/wrolpi?style=flat-square)](https://github.com/lrnselfreliance/wrolpi/blob/master/LICENSE)
[![Discord](https://img.shields.io/discord/900430987987681330?label=Discord&logo=discord)](https://discord.gg/HrwFk7nqA2)
[![Gitpod](https://img.shields.io/badge/Contribute%20with-Gitpod-908a85?logo=gitpod)](https://gitpod.io/#https://github.com/lrnselfreliance/wrolpi)

**Create your own off-grid library.**

<p align="center">
  <img width="256px" src="https://raw.githubusercontent.com/lrnselfreliance/wrolpi/master/icon.png" alt='WROLPi Logo'>
</p>

WROLPi is a self-contained collection of software to help you survive the world Without Rule of Law.

WROLPi is intended to be run on a Raspberry Pi with an optional external drive attached. It serves up it's own Wi-Fi
network so that any user with a laptop/tablet/phone can connect and use the library created by the maintainer.

# Table of Contents

* [Features](#features)
* [Demo](#demo)
* [Download](#download)
* [Try WROLPi](#try-wrolpi)
* [Install WROLPi](INSTALL.md)
* [Docker Documentation](docker/README.md)
* [Charter](#charter)
* [Upgrading WROLPi](UPGRADE.md)
* [Join](#join)

# Features

- [x] Videos
- [x] Web Archives
- [x] Maps
- [x] Wikipedia
- [x] File search
- [x] eBooks (EPUB / PDFs)
- [x] Wi-Fi Hotspot
- [x] Universal search
- [x] Food Inventory management
- [x] One-Time pad generator, encrypter/decrypter
- [ ] Synchronizer/duplicator
- [ ] Food storage calculator

## Module features matrix

| **Module**     | **View** | **Search** | **Download** | **Project**                                                |
|----------------|----------|:-----------|--------------|------------------------------------------------------------|
| Videos         | yes      | yes        | yes          | [yt-dlp](https://github.com/yt-dlp/yt-dlp)                 |
| Web Archives   | yes      | yes        | yes          | [Singlefile](https://github.com/gildas-lormeau/SingleFile) |
| Wikipedia      | yes      | yes        | yes          | [Kiwix](https://www.kiwix.org)                             |
| eBooks         | yes      | yes        | planned      | EPUB/PDF                                                   |
| Map            | yes      | yes        | yes          | [Protomaps](https://protomaps.com/)                        |
| Podcasts/Audio | yes      | planned    | planned      |                                                            |

# Demo

<a href="https://www.youtube.com/watch?v=Qz-FuenRylQ"> ![YouTube Demo Video](https://raw.githubusercontent.com/lrnselfreliance/wrolpi/master/demo_link.jpg)</a>

# Download

Images are available at [wrolpi.org](https://wrolpi.org)

# Try WROLPi!

You can try out WROLPi by running the docker containers.

1. [Install docker-ce](https://docs.docker.com/install/linux/docker-ce/debian/) and
   [docker-compose](https://docs.docker.com/compose/install/)
2. Copy the latest WROLPi code.
    * `git clone https://github.com/lrnselfreliance/wrolpi.git`
3. Change directory into the code base.
    * `cd wrolpi`
4. Initialize git submodules
    * `git submodule update --init`
5. Build the containers.
    * `docker-compose build --parallel`
6. Create volumes.
    * `docker volume create --name=openstreetmap-data`
    * `docker volume create --name=openstreetmap-rendered-tiles`
7. Start the database.
    * `docker-compose up -d db`
8. Initialize the database.
    * `docker-compose run --rm api db upgrade`
9. Start the docker containers.
    * `docker-compose up`
10. Browse to WROLPi.
    * https://0.0.0.0:8443

More Docker documentation is available in [docker/README.md](docker/README.md)

# Install WROLPi

Full installation instructions are in [INSTALL.md](INSTALL.md).  Pick the option that matches your hardware:

* **[WROLPi Portable (Live USB)](INSTALL.md#wrolpi-portable-live-usb)** — boot a complete WROLPi from a USB stick on any x86 PC or laptop.  Nothing is installed to the computer; the first boot creates a persistence partition on the USB so your library, database, and configuration survive reboots.
* **[Debian 12](INSTALL.md#debian-12-install)** — install WROLPi onto an x86 PC or laptop.
* **[Raspberry Pi](INSTALL.md#raspberry-pi-install)** — install WROLPi onto a Raspberry Pi with an external drive.
* **[Docker](docker/README.md)** — run the WROLPi containers on an existing Linux host.

# Charter

## Guiding Principals

1. Storage is cheaper than power.
2. Two is one, one is none.
3. Run silently.
4. Primary, secondary, tertiary.
5. Secure as a bookshelf in your home.

## Physical properties

1. A WROLPi instance should be capable of running with a minimal of hardware:
    * Raspberry Pi
    * SD card
    * External USB hard drive
    * Power supply and cables
    * Wi-Fi USER device such as a phone, tablet, or laptop.
2. A WROLPi instance should consume a minimal amount of electricity during WROL event. It is expected power will be
   scarce when WROLPi is needed most.

## User expectations

1. A WROLPi instance should be run and maintained by a person (MAINTAINER) with a moderate amount of Linux and Raspberry
   Pi experience. It is expected that they should be able to do this using only the documentation on their WROLPi.

## Software properties and capabilities

1. A WROLPi instance should be able to "factory-reset" itself without any outside services.
2. WROLPi should function completely without any internet services.
3. A user should have easy access to their data if WROLPi fails:
    * For example, a user can watch their videos by navigating a short and intuitive directory structure and opening the
      video in their preferred video player.
4. WROLPi should be self-documented. The UI should contain a tutorial for USERS as well as the MAINTAINER.
    * If the UI isn't functional, the code should be documented such that a user can restore functionality.
5. WROLPi should favor pre-processing, rather than processing during a WROL event. Such as re-encoding a video, or
   processing captions. This is to ensure that when a user adds content during non-WROL time, the processing for optimum
   performance is already done for a WROL event.

# Join!

<p>
   <img src="https://raw.githubusercontent.com/lrnselfreliance/wrolpi/master/join_discord.png" alt='Discord QR Code'>
</p>

[Join our Discord](https://discord.gg/HrwFk7nqA2)
