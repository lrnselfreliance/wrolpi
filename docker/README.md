# WROLPi Docker

Development and testing environment using Docker containers.

## Quick Start

```bash
git clone https://github.com/lrnselfreliance/wrolpi.git
cd wrolpi
git submodule update --init
docker-compose build --parallel
docker volume create --name=openstreetmap-data
docker volume create --name=openstreetmap-rendered-tiles
docker-compose up -d db
docker-compose run --rm api db upgrade
docker-compose up
```

Browse to https://localhost:8443

## Services

| Service        | Port(s)                              | Description                 |
|----------------|--------------------------------------|-----------------------------|
| **web**        | 8080 (HTTP), 8443 (HTTPS), 8084-8086 | Caddy reverse proxy         |
| **api**        | 8081                                 | Sanic API server            |
| **app**        | (via web)                            | React frontend              |
| **controller** | 8087                                 | System management (FastAPI) |
| **db**         | 5432                                 | PostgreSQL 12               |
| **archive**    | 8083                                 | SingleFile/Readability      |
| **zim**        | (via web:8085)                       | Kiwix                       |
| **help**       | (via web:8086)                       | MkDocs documentation        |
| **map**        | (via web:8084)                       | OpenStreetMap tile server   |

## TLS Certificates

WROLPi uses a two-tier PKI for HTTPS. A **root CA** is generated once and persists
in the media directory. A **leaf certificate** is regenerated on every container start
to pick up hostname and IP changes.

### How it works

1. On first start, the `web` container generates a root CA at `/opt/media/config/ssl/`.
2. A leaf cert signed by the root CA is created at `/etc/ssl/caddy/` inside the container.
3. Caddy serves HTTPS on ports 443, 8084, 8085, and 8086 using the leaf cert.
4. Port 80 serves an HTTP landing page where users can download the root CA.

### Trusting the certificate

1. Browse to `http://<host-ip>:8080` to see the landing page with download link and
   platform-specific trust instructions.
2. Download and install the root CA on your device.
3. All HTTPS ports will work without browser warnings.

The root CA only needs to be trusted once. Leaf certs can be regenerated (hostname
change, container rebuild) without needing to re-trust.

### Name Constraints

The root CA is restricted to local/private networks only via X.509 Name Constraints.
Even if the CA key were compromised, it cannot sign certificates for public domains.

Permitted:

- DNS: `*.local`, `localhost`
- IPv4: `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
- IPv6: `::1`, `fc00::/7` (unique local), `fe80::/10` (link-local)

### EXTRA_SANS

The Docker container cannot discover the host's real LAN IP. Set `EXTRA_SANS` in a
`.env` file so the leaf certificate includes your host's IP and hostname:

```bash
# .env
EXTRA_SANS=IP:10.0.0.5,DNS:myhost.local
```

Each entry must have a type prefix (`IP:` or `DNS:`). Multiple entries are
comma-separated. After changing `EXTRA_SANS`, restart the web container:

```bash
docker compose up -d --build web
```

### Regenerating the root CA

If you need to regenerate the root CA (e.g. after updating the certificate
generation script), delete the old CA files and rebuild:

```bash
rm test/config/ssl/ca.crt test/config/ssl/ca.key
docker compose up -d --build web
```

All devices will need to re-download and re-trust the new CA from
`http://<host-ip>:8080/ca.crt`.

## Volumes

The `test/` directory is mounted to `/opt/media` inside containers, serving as the
media directory for development. Certificate files, configs, and downloaded content
are stored here.

Two external volumes are required for the map service:

```bash
docker volume create --name=openstreetmap-data
docker volume create --name=openstreetmap-rendered-tiles
```

## Environment Variables

| Variable          | Default        | Description                                  |
|-------------------|----------------|----------------------------------------------|
| `MEDIA_DIRECTORY` | `/opt/media`   | Media directory inside containers            |
| `EXTRA_SANS`      | (empty)        | Additional SANs for the TLS leaf certificate |
| `WEB_HOST`        | `0.0.0.0`      | Host bind address for the web service        |
| `WEB_PORT`        | `8080`         | HTTP port                                    |
| `WEB_HTTPS_PORT`  | `8443`         | HTTPS port                                   |
| `REACT_APP_API`   | `0.0.0.0:8081` | API bind address                             |
| `UID`             | `1000`         | User ID for api/app containers               |
| `GID`             | `1000`         | Group ID for api/app containers              |

## Upgrading

See [UPGRADE.md](../UPGRADE.md) for upgrade instructions.
