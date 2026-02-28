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

# Upgrade Controller
upgrade_controller() {
    echo "Upgrading WROLPi Controller..."

    # Stop Controller during upgrade
    systemctl stop wrolpi-controller || true

    # Create Controller venv if it doesn't exist
    if [ ! -d /opt/wrolpi/controller/venv ]; then
        echo "Creating Controller virtual environment..."
        python3 -m venv /opt/wrolpi/controller/venv
    fi

    # Clear bytecode cache before upgrading.
    find /opt/wrolpi/controller/venv -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || :
    find /opt/wrolpi/controller/venv -name "*.pyc" -delete 2>/dev/null || :

    # Update dependencies
    echo "Updating Controller dependencies..."
    /opt/wrolpi/controller/venv/bin/pip install --upgrade pip
    /opt/wrolpi/controller/venv/bin/pip install --upgrade -r /opt/wrolpi/controller/requirements.txt

    # Start the Controller.
    systemctl daemon-reload
    systemctl start wrolpi-controller
}

upgrade_controller || echo "Controller upgrade failed, continuing..."

# Upgrade WROLPi Help.
/opt/wrolpi/scripts/install_help_service.sh || echo "Help install failed."

# Get map db blob, if it is missing.
MAP_DB_BLOB=/opt/wrolpi-blobs/map-db-gis.dump
if [[ ! -f ${MAP_DB_BLOB} || ! -s ${MAP_DB_BLOB} ]]; then
  echo "Downloading new map blob (1.2 GB)..."
  wget https://wrolpi.nyc3.cdn.digitaloceanspaces.com/map-db-gis.dump -O ${MAP_DB_BLOB}
fi
if [[ -f /opt/wrolpi-blobs/gis-map.dump.gz && -s ${MAP_DB_BLOB} ]]; then
  # Remove old blob now that we have the new one.
  rm /opt/wrolpi-blobs/gis-map.dump.gz
fi

# Migrate map DB if necessary.  Do this before repair because it will reset map if map db is empty.
/opt/wrolpi/wrolpi/scripts/migrate_map_db.sh || echo "Map DB migration failed."

# Install any configs, restart services.
/opt/wrolpi/repair.sh
