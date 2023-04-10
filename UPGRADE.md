# Upgrading WROLPi

# Table of Contents

* [Upgrading Docker containers](#upgrading-docker-containers)
* [Upgrading Raspberry Pi or Debian 11 Installation](#upgrading-raspberry-pi-or-debian-11-installation)

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

## Upgrading Raspberry Pi or Debian 11 Installation

1. Run the upgrade script
    * `sudo /bin/bash /opt/wrolpi/upgrade.sh`
