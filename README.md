# WROLPi

[![Build Status](https://img.shields.io/circleci/build/github/lrnselfreliance/wrolpi/release?label=release%20build)](https://app.circleci.com/pipelines/github/lrnselfreliance/wrolpi?branch=release&filter=all)
[![License: GPL v3](https://img.shields.io/github/license/lrnselfreliance/wrolpi?style=flat-square)](https://github.com/lrnselfreliance/wrolpi/blob/master/LICENSE)
[![Discord](https://img.shields.io/discord/900430987987681330?label=Discord&logo=discord)](https://discord.gg/HrwFk7nqA2)

**Create your own off-grid library.**

<p align="center">
  <img width="256px" src="https://raw.githubusercontent.com/lrnselfreliance/wrolpi/master/icon.png" alt='WROLPi Logo'>
</p>

WROLPi is a self-contained collection of software to help you survive the world Without Rule of Law.

WROLPi is intended to be run on a Raspberry Pi with an optional external drive attached. It serves up it's own Wi-Fi
network so that any user with a laptop/tablet/phone can connect and use the library created by the maintainer.

# WARNING WROLPi is under active development!

- WROLPi is in Beta!
- Expect things to change!

# Table of Contents

* [Features](#features)
* [Demo](#demo)
* [Try WROLPi](#try-wrolpi)
* [Debian 11 Install](#debian-11-install)
* [Raspberry Pi Install](#raspberrypi-install)
* [Charter](#charter)
* [Upgrading WROLPi](UPGRADE.md)
* [Join](#charter)

# Features

- [x] Video player & downloader
- [x] Web archiver
- [x] Map viewer
- [x] Wi-Fi Hotspot
- [x] Universal search
- [x] Food Inventory management
- [x] One-Time pad generator, encrypter/decrypter
- [ ] eBook viewer
- [ ] Wiki viewer & downloader
- [ ] Synchronizer and/or duplicator
- [ ] Food storage calculator
- [ ] Podcast player & downloader

# Demo

<a href="https://www.youtube.com/watch?v=Qz-FuenRylQ"> ![YouTube Demo Video](https://raw.githubusercontent.com/lrnselfreliance/wrolpi/master/demo_link.jpg)</a>

# Try WROLPi!

You can try out WROLPi by running the docker containers.

1. [Install docker-ce](https://docs.docker.com/install/linux/docker-ce/debian/) and
   [docker-compose](https://docs.docker.com/compose/install/)
2. Copy the latest WROLPi code
    * `git clone https://github.com/lrnselfreliance/wrolpi.git`
3. Change directory into the code base
    * `cd wrolpi`
4. Build the containers
    * `docker-compose build --parallel`
5. Create volumes
    * `docker volume create --name=openstreetmap-data`
    * `docker volume create --name=openstreetmap-rendered-tiles`
6. Start the database.
    * `docker-compose up -d db`
7. Initialize the database
    * `docker-compose run --rm api db upgrade`
8. Start the docker containers
    * `docker-compose up`
9. Browse to WROLPi
    * http://0.0.0.0:8080

# Debian 11 Install

Install WROLPi onto a fresh Debian 11 system.

**Warning: this will clobber anything else on the system!  Do not run this installation script elsewhere!**

1. Install [Debian 11](https://www.debian.org/) onto a laptop or other computer.
2. Login to the new system.
3. Get the WROLPi installation script
    * `wget https://raw.githubusercontent.com/lrnselfreliance/wrolpi/release/install.sh -O /tmp/install.sh`
4. Run the installation script
    * `sudo /bin/bash /tmp/install.sh`
5. Start WROLPi
    * `sudo systemctl start wrolpi.target`
6. Browse to the IP address of your WROLPi!

# RaspberryPi Install

Install WROLPi onto a fresh Raspberry Pi.

**Warning: this will clobber anything else on the Raspberry Pi!  Do not run this installation script elsewhere!**

1. Install [Ubuntu Server 20.04](https://cdimage.ubuntu.com/releases/20.04/release/) onto a RaspberryPi.
2. Login to the new RaspberryPi.
3. Get the WROLPi installation script
    * `wget https://raw.githubusercontent.com/lrnselfreliance/wrolpi/release/install.sh -O /tmp/install.sh`
4. Run the installation script
    * `sudo /bin/bash /tmp/install.sh`
5. Start WROLPi
    * `sudo systemctl start wrolpi.target`
6. Join the Hotspot or browse to the IP address of your WROLPi!

# Charter

## Physical properties

1. A WROLPi instance should be capable of running with a minimal of hardware:
    * Raspberry Pi
    * SD card
    * External USB hard drive
    * Power supply and cables
    * WiFi USER device such as a phone, tablet, or laptop.
1. A WROLPi instance should consume a minimal amount of electricity during WROL event. It is expected power will be
   scarce when WROLPi is needed most.

## User expectations

1. A WROLPi instance should be run and maintained by a person (MAINTAINER) with a moderate amount of Linux and Raspberry
   Pi experience. It is expected that they should be able to do this using only the documentation on their WROLPi.

## Software properties and capabilities

1. A WROLPi instance should be able to "factory-reset" itself without any outside services.
1. WROLPi should function completely without any internet services.
1. A user should have easy access to their data if WROLPi fails:
    * For example, a user can watch their videos by navigating a short and intuitive directory structure and opening the
      video in their preferred video player.
1. WROLPi should be self-documented. The UI should contain a tutorial for USERS as well as the MAINTAINER.
    * If the UI isn't functional, the code should be documented such that a user can restore functionality.
1. WROLPi should favor pre-processing, rather than processing during a WROL event. Such as re-encoding a video, or
   processing captions. This is to ensure that when a user adds content during non-WROL time, the processing for optimum
   performance is already done for a WROL event.

# Join!

<p>
   <img src="https://raw.githubusercontent.com/lrnselfreliance/wrolpi/master/join_discord.png" alt='Discord QR Code'>
</p>

[Join our Discord](https://discord.gg/HrwFk7nqA2)
