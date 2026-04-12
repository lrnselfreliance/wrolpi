#!/usr/bin/env bash
# Installs PMTiles tools and migrates from the old Leaflet/renderd/Apache2 map stack.
# This script is idempotent — safe to run multiple times.
# Called by upgrade.sh during the upgrade process.

set -e
set -x

# --- Install/upgrade pmtiles CLI ---

install_pmtiles() {
    PMTILES_VERSION="v1.30.1"
    ARCH=$(uname -m)
    if [ "$ARCH" = "aarch64" ]; then
        PMTILES_ARCH="arm64"
    elif [ "$ARCH" = "x86_64" ]; then
        PMTILES_ARCH="amd64"
    else
        echo "Unsupported architecture for pmtiles: $ARCH"
        return 1
    fi

    # Check if already installed at correct version.
    if command -v pmtiles &>/dev/null; then
        CURRENT=$(pmtiles version 2>&1 | head -1 | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' || echo "")
        if [ "$CURRENT" = "$PMTILES_VERSION" ]; then
            echo "pmtiles ${PMTILES_VERSION} already installed"
            return 0
        fi
    fi

    echo "Installing pmtiles ${PMTILES_VERSION} for ${ARCH}..."
    curl -fsSL "https://github.com/protomaps/go-pmtiles/releases/download/${PMTILES_VERSION}/go-pmtiles_${PMTILES_VERSION#v}_Linux_${PMTILES_ARCH}.tar.gz" \
      | tar -xz -C /usr/local/bin/ pmtiles
    chmod +x /usr/local/bin/pmtiles
    pmtiles version
}

install_pmtiles || echo "pmtiles CLI installation failed, continuing..."

# --- Install/upgrade tippecanoe (for map search index building) ---

install_tippecanoe() {
    TIPPECANOE_VERSION="2.79.0"

    # Check if already installed at correct version.
    if command -v tippecanoe-decode &>/dev/null; then
        CURRENT=$(tippecanoe --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "")
        if [ "$CURRENT" = "$TIPPECANOE_VERSION" ]; then
            echo "tippecanoe ${TIPPECANOE_VERSION} already installed"
            return 0
        fi
    fi

    echo "Building tippecanoe ${TIPPECANOE_VERSION}..."
    apt-get install -y build-essential libsqlite3-dev zlib1g-dev

    TIPPECANOE_BUILD_DIR=$(mktemp -d)
    curl -fsSL "https://github.com/felt/tippecanoe/archive/refs/tags/${TIPPECANOE_VERSION}.tar.gz" \
      | tar -xz -C "${TIPPECANOE_BUILD_DIR}" --strip-components=1
    cd "${TIPPECANOE_BUILD_DIR}" && make -j$(nproc) && make install
    rm -rf "${TIPPECANOE_BUILD_DIR}"
    tippecanoe --version
}

install_tippecanoe || echo "tippecanoe installation failed, continuing..."

# --- Migrate from old map stack (runs once) ---

MARKER_FILE="/opt/wrolpi/.protomaps_installed"

if [ -f "${MARKER_FILE}" ]; then
  echo "Protomaps migration already completed."
  exit 0
fi

echo "Migrating map stack to Protomaps (MapLibre GL JS + PMTiles)..."

# --- Step 1: Stop and disable old map services ---

echo "Stopping old map services..."
systemctl stop renderd 2>/dev/null || :
systemctl stop apache2 2>/dev/null || :
systemctl stop postgresql@15-map.service 2>/dev/null || :

systemctl disable renderd 2>/dev/null || :
systemctl disable apache2 2>/dev/null || :
systemctl disable postgresql@15-map.service 2>/dev/null || :

# --- Step 2: Uninstall old map packages ---

echo "Removing old map packages..."
apt-get remove -y --purge apache2 apache2-dev apache2-doc libapache2-mod-tile renderd osm2pgsql 2>/dev/null || :
apt-get autoremove -y 2>/dev/null || :

# --- Step 3: Drop the map PostgreSQL cluster ---

echo "Removing map PostgreSQL cluster..."
if pg_lsclusters 2>/dev/null | grep -q "15.*map"; then
  pg_dropcluster --stop 15 map 2>/dev/null || :
fi

# Remove the map database blob (no longer needed, saves ~1.2 GB).
if [ -f /opt/wrolpi-blobs/map-db-gis.dump ]; then
  chattr -i /opt/wrolpi-blobs/map-db-gis.dump 2>/dev/null || :
  rm -f /opt/wrolpi-blobs/map-db-gis.dump
  echo "Removed map-db-gis.dump blob."
fi

# --- Step 4: Clean up old config files ---

rm -f /etc/renderd.conf
rm -f /etc/apache2/ports.conf
rm -f /etc/apache2/conf-available/mod_tile.conf
rm -f /etc/apache2/sites-available/000-default.conf
rm -rf /etc/systemd/system/postgresql@15-map.service.d
rm -f /var/www/html/leaflet.js /var/www/html/leaflet.css
# Remove old .pgpass entry for the map database.
if [ -f /home/wrolpi/.pgpass ]; then
  sed -i '/5433/d' /home/wrolpi/.pgpass
fi

# --- Step 5: Update wrolpi.target to remove old services ---

# The target file is copied from the repo by repair.sh, but update the installed copy now.
if [ -f /etc/systemd/system/wrolpi.target ]; then
  sed -i 's/ renderd\.service//' /etc/systemd/system/wrolpi.target
  sed -i 's/ apache2\.service//' /etc/systemd/system/wrolpi.target
  sed -i 's/ postgresql@15-map\.service//' /etc/systemd/system/wrolpi.target
fi

systemctl daemon-reload

# --- Step 6: Mark migration as complete ---

touch "${MARKER_FILE}"
chown wrolpi:wrolpi "${MARKER_FILE}"

echo "Protomaps migration completed successfully."
echo "Map files (.pmtiles) should be placed in /media/wrolpi/map/"
echo "The map viewer is served by Caddy on port 8084."
