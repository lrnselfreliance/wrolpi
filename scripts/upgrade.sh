#! /usr/bin/env bash
# Installs any new dependencies of the App and API.  Uses internet.

set -e
set -x

# Ensure help service is always restarted, but preserve exit code
cleanup() {
    local exit_code=$?
    systemctl restart wrolpi-help.service || :
    exit $exit_code
}
trap cleanup EXIT

# Upgrade Controller first so users can monitor the rest of the upgrade.
upgrade_controller() {
    echo "Upgrading WROLPi Controller..."

    # Create Controller venv if it doesn't exist
    if [ ! -d /opt/wrolpi/controller/venv ]; then
        echo "Creating Controller virtual environment..."
        python3 -m venv /opt/wrolpi/controller/venv
    fi

    # Clear bytecode cache before upgrading.
    find /opt/wrolpi/controller/venv -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || :
    find /opt/wrolpi/controller/venv -name "*.pyc" -delete 2>/dev/null || :

    # Install dependencies while Controller is still running to minimize downtime.
    echo "Updating Controller dependencies..."
    /opt/wrolpi/controller/venv/bin/pip install --upgrade pip
    /opt/wrolpi/controller/venv/bin/pip install --upgrade -r /opt/wrolpi/controller/requirements.txt

    # Dependencies are ready, now restart the Controller as quickly as possible.
    systemctl daemon-reload
    systemctl restart wrolpi-controller
}

upgrade_controller || echo "Controller upgrade failed, continuing..."

# Install any App dependencies.
cd /opt/wrolpi/app || exit 1
npm install || npm install || npm install || npm install # try install multiple times  :(

# Install/upgrade Deno runtime.
upgrade_deno() {
    DENO_VERSION="v2.2.4"
    ARCH=$(uname -m)
    if [ "$ARCH" = "aarch64" ]; then
        DENO_ARCH="aarch64-unknown-linux-gnu"
    elif [ "$ARCH" = "x86_64" ]; then
        DENO_ARCH="x86_64-unknown-linux-gnu"
    else
        echo "Unsupported architecture for Deno: $ARCH"
        return 1
    fi

    # Check if Deno is already installed at the correct version.
    if command -v deno &> /dev/null; then
        CURRENT_VERSION=$(deno --version | head -n1 | awk '{print "v"$2}')
        if [ "$CURRENT_VERSION" = "$DENO_VERSION" ]; then
            echo "Deno ${DENO_VERSION} already installed"
            return 0
        fi
    fi

    echo "Installing Deno ${DENO_VERSION} for ${ARCH}..."
    curl -fsSL "https://github.com/denoland/deno/releases/download/${DENO_VERSION}/deno-${DENO_ARCH}.zip" -o /tmp/deno.zip
    unzip -o /tmp/deno.zip -d /usr/local/bin/
    chmod +x /usr/local/bin/deno
    rm /tmp/deno.zip
    deno --version
}

upgrade_deno || echo "Deno upgrade failed, continuing..."

# Clear Python bytecode cache before upgrading packages.
echo "Clearing Python bytecode cache..."
find /opt/wrolpi/venv -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || :
find /opt/wrolpi/venv -name "*.pyc" -delete 2>/dev/null || :

# Install any new Python requirements.
/opt/wrolpi/venv/bin/pip3 install --upgrade -r /opt/wrolpi/requirements.txt
# Upgrade the WROLPi database.
(cd /opt/wrolpi && /opt/wrolpi/venv/bin/python3 /opt/wrolpi/main.py db upgrade)

# Upgrade WROLPi Help.
/opt/wrolpi/scripts/install_help_service.sh || echo "Help install failed."

# Migrate from old Leaflet/renderd/Apache2 map stack to MapLibre GL JS + PMTiles.
/opt/wrolpi/scripts/install_protomaps.sh || echo "Protomaps migration failed."

# Download map fonts blob if missing.
MAP_FONTS_BLOB=/opt/wrolpi-blobs/map-fonts.tar.gz
if [[ ! -f ${MAP_FONTS_BLOB} || ! -s ${MAP_FONTS_BLOB} ]]; then
  echo "Downloading map fonts..."
  mkdir -p /tmp/map-fonts-dl
  curl -fsSL https://github.com/protomaps/basemaps-assets/archive/refs/heads/main.tar.gz \
    | tar -xz --strip-components=1 -C /tmp/map-fonts-dl basemaps-assets-main/fonts
  tar -czf "${MAP_FONTS_BLOB}" -C /tmp/map-fonts-dl fonts
  rm -rf /tmp/map-fonts-dl
fi || echo "Map fonts download failed, continuing..."

# Download map overview blob if missing (42 MB, provides global zoom 0-6).
MAP_OVERVIEW_BLOB=/opt/wrolpi-blobs/map-overview.pmtiles
if [[ ! -f ${MAP_OVERVIEW_BLOB} || ! -s ${MAP_OVERVIEW_BLOB} ]]; then
  echo "Downloading map overview..."
  curl -fsSL https://wrolpi.nyc3.cdn.digitaloceanspaces.com/maps/map-overview.pmtiles \
    -o "${MAP_OVERVIEW_BLOB}"
fi || echo "Map overview download failed, continuing..."

# Migrate from nginx to Caddy if necessary.
if ! command -v caddy &>/dev/null; then
  echo "Installing Caddy (replacing nginx)..."
  # Disable and stop nginx if it was previously used.
  systemctl stop nginx 2>/dev/null || :
  systemctl disable nginx 2>/dev/null || :
  # Install Caddy from official apt repo.
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
fi

# Install Samba if not already installed.
if ! command -v smbd &>/dev/null; then
  echo "Installing Samba..."
  apt-get update
  apt-get install -y samba
fi

# Install gnome-disk-utility if not already installed (provides desktop disk management GUI).
if ! command -v gnome-disks &>/dev/null; then
  echo "Installing gnome-disk-utility..."
  apt-get update
  apt-get install -y gnome-disk-utility
fi

# Clean up stale landing page (Controller now serves port 80 directly).
rm -f /var/www/landing.html

# Install any configs, restart services.
/opt/wrolpi/repair.sh
