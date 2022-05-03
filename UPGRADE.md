# Upgrading WROLPi

# Table of Contents

* [Upgrading Docker containers](#upgrading-docker-containers)
* [Upgrading Raspberry Pi or Debian 11 Installation](#upgrading-raspberry-pi-or-debian-11-installation)

## Upgrading Docker containers

1. Pull the latest master
    * `git pull origin master --ff`
2. Stop docker containers
    * `docker-compose stop`
3. Build all docker containers
    * `docker-compose build --parallel`
4. Turn on the database
    * `docker-compose up -d db`
5. Upgrade the database
    * `docker-compose run --rm api db upgrade`
6. Start all docker containers
    * `docker-compose up -d`

## Upgrading Raspberry Pi or Debian 11 Installation

1. Get the latest release install script
    * `wget https://raw.githubusercontent.com/lrnselfreliance/wrolpi/release/install.sh -O /tmp/install.sh`
2. Run the installation script
    * `sudo /bin/bash /tmp/install.sh`
3. Start WROLPi
    * `sudo systemctl start wrolpi.target`
