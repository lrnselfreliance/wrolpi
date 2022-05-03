# Upgrading WROLPi

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
