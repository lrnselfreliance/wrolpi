#! /usr/bin/env bash
# Pulls, builds, and initializes the development Docker containers.

docker volume create --name=openstreetmap-data
docker volume create --name=openstreetmap-rendered-tiles
git submodule update --init
docker compose pull
docker compose build --parallel
docker compose up -d db
docker compose run --rm api db upgrade
docker compose stop
