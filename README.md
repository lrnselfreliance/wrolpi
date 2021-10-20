# WROLPi

[![Build Status](https://img.shields.io/travis/lrnselfreliance/wrolpi?style=flat-square)](https://travis-ci.com/lrnselfreliance/wrolpi)
[![License: GPL v3](https://img.shields.io/github/license/lrnselfreliance/wrolpi?style=flat-square)](https://github.com/lrnselfreliance/wrolpi/blob/master/LICENSE)

**Take your internet, off-grid.**

<p align="center">
  <img width="256px" src="https://raw.githubusercontent.com/lrnselfreliance/wrolpi/master/icon.png" alt='WROLPi Logo'>
</p>

WROLPi is a self-contained collection of software (on a Raspberry Pi) to help you survive the world Without Rule of Law.

WROLPi is intended to be run on a Raspberry Pi with an optional external drive attached. It serves up it's own wifi
network so that any person with a laptop/tablet/phone can connect and use the data previously collected by the user.

# WARNING WROLPi is under active development!

- WROLPi is in early Alpha!
- Expect things to change!

# Minimal Install

WROLPi runs in a couple Docker containers. Let's get the prerequisites installed...

1. [Install docker-ce](https://docs.docker.com/install/linux/docker-ce/debian/) and
   [docker-compose](https://docs.docker.com/compose/install/)
1. Copy the latest WROLPi code
    * `git clone git@github.com:lrnselfreliance/wrolpi.git`
1. Change directory into the code base
    * `cd wrolpi`
1. Build the docker containers
    * `docker-compose build --parallel`
1. Start the docker containers
    * `docker-compose up`
1. Navigate to WROLPi
    * http://0.0.0.0:8080

# Features

- [x] Video player & downloader
- [x] One-Time pad generator, encrypter/decrypter
- [x] Web archiver
- [x] Inventory management
- [ ] Wi-Fi Hotspot
- [ ] Universal search
- [ ] Map viewer & downloader
- [ ] eBook viewer
- [ ] Wiki viewer & downloader
- [ ] Synchronizer and/or duplicator
- [ ] Food storage calculator
- [ ] Podcast player & downloader

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

[Join our Discord](https://discord.gg/HrwFk7nqA2)
