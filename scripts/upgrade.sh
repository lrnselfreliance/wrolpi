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

# --- Debian 12 (bookworm) hard cutoff --------------------------------------
# WROLPi's Debian 12 line ends at the signed tag `debian12-final`.  Everything
# after it (the Postgres->SQLite move and the Debian 13 rebase) requires a
# fresh Debian 13 (trixie) system; there is no supported in-place 12 -> 13
# upgrade.  ./upgrade.sh has already fetched and checked out the latest
# release by the time we run, so on a Debian 12 machine we pin back to
# `debian12-final` and never advance past it.  On Debian 13+ this is a no-op
# and the normal upgrade proceeds.
GUARD_TAG="debian12-final"
GUARD_KEY="/opt/wrolpi/wrolpi/roland@learningselfreliance.com.gpg"

# True only on Debian 13 (trixie) or newer.  A missing or non-numeric
# VERSION_ID is treated as "older" so the frozen line fails safe (pins).
os_is_debian_13_or_newer() {
    local vid=""
    [ -r /etc/os-release ] && vid=$(awk -F= '$1=="VERSION_ID"{gsub(/"/,"",$2);print $2}' /etc/os-release)
    case "${vid}" in
        '' | *[!0-9]*) return 1 ;;
    esac
    [ "${vid}" -ge 13 ]
}

# Verify the guard commit is signed by the trusted WROLPi key before we check
# it out and execute it.  ./upgrade.sh only verified the release tip it landed
# on; `debian12-final` is off that line, so we re-verify here with a throwaway
# keyring (same trust model as ./upgrade.sh).
verify_guard_commit() {
    local ghome rc=1
    ghome=$(mktemp -d)
    if GNUPGHOME="${ghome}" gpg --batch --quiet --import "${GUARD_KEY}" 2>/dev/null; then
        # Mark the pinned key ultimately trusted to silence cosmetic web-of-trust
        # warnings; validity (not trust) is what verify-commit actually checks.
        GNUPGHOME="${ghome}" gpg --batch --list-keys --with-colons 2>/dev/null \
            | awk -F: '/^fpr:/ {print $10":6:"; exit}' \
            | GNUPGHOME="${ghome}" gpg --batch --quiet --import-ownertrust 2>/dev/null || :
        GNUPGHOME="${ghome}" git -C /opt/wrolpi verify-commit "${GUARD_TAG}^{commit}" 2>&1 && rc=0
    fi
    rm -rf "${ghome}"
    return "${rc}"
}

debian12_guard() {
    if os_is_debian_13_or_newer; then
        return 0
    fi

    # Debian 12 (or older): make sure the cutoff tag is present AND current.
    # `debian12-final` is off the release line, so a plain fetch of the branch
    # would not follow it.  Force (+ / --force) so a moved tag (e.g. a bumped
    # final release) overwrites a stale local tag instead of being rejected as
    # "would clobber existing tag" — otherwise the guard pins to the old target.
    # Safe to force: the commit's signature is verified before checkout below.
    git -C /opt/wrolpi fetch origin "+refs/tags/${GUARD_TAG}:refs/tags/${GUARD_TAG}" 2>/dev/null \
        || git -C /opt/wrolpi fetch --force --tags origin 2>/dev/null || :

    # --verify --quiet: fail cleanly (empty, non-zero) instead of echoing the
    # unresolved arg when the tag is absent.
    local head target
    head=$(git -C /opt/wrolpi rev-parse --verify --quiet HEAD 2>/dev/null || echo none)
    target=$(git -C /opt/wrolpi rev-parse --verify --quiet "${GUARD_TAG}^{commit}" 2>/dev/null || echo none)

    if [ "${target}" = "none" ]; then
        echo "ERROR: Debian 12 cutoff tag '${GUARD_TAG}' not found; refusing to run newer code on Debian 12."
        exit 10
    fi

    if [ "${head}" != "${target}" ]; then
        # ./upgrade.sh checked out a newer release; roll back to the last
        # supported commit, then hand off to ITS copy of this script via exec so
        # we stop running the newer (already-overwritten) version.
        if ! verify_guard_commit; then
            echo "ERROR: '${GUARD_TAG}' is not signed by the trusted WROLPi key; aborting."
            exit 11
        fi
        echo "Debian 12 detected: pinning WROLPi to its final supported version (${GUARD_TAG})."
        git -C /opt/wrolpi checkout -f -B release "${GUARD_TAG}" \
            || { echo "ERROR: could not check out ${GUARD_TAG}; aborting."; exit 12; }
        # Loop guard: never re-exec unless the rollback actually landed on the target.
        if [ "$(git -C /opt/wrolpi rev-parse HEAD)" != "${target}" ]; then
            echo "ERROR: rollback did not land on ${GUARD_TAG}; aborting."
            exit 13
        fi
        exec /opt/wrolpi/scripts/upgrade.sh "$@"
    fi

    # Already on the final supported commit: warn loudly, then fall through so
    # this (final) version's normal upgrade runs and leaves the box healthy with
    # services restarted.
    cat <<'EOF'

================================================================================
  This is the FINAL WROLPi version for Debian 12 (bookworm).

  No further updates will be installed on Debian 12.  To keep receiving
  updates, reinstall WROLPi on Debian 13 (trixie):
    * Download the latest image from https://wrolpi.org
    * Write it to your SD card / USB and boot it.
    * Reconnect your media drive; your files and configuration are preserved
      on the drive and will be re-indexed automatically.
================================================================================

EOF
}

debian12_guard "$@"
# ---------------------------------------------------------------------------

# --- Rebuild virtual environments after a Python major-version change -------
# A Debian major upgrade (e.g. 12 -> 13) replaces /usr/bin/python3 (3.11 -> 3.13).
# The existing venvs still resolve their `python3` to the system interpreter,
# but their packages live in lib/python3.11/site-packages, which the new
# interpreter never searches -- so every import fails and `pip install --upgrade`
# cannot repair them.  Detect this by comparing each venv's recorded Python
# version against the current one, and do a full rebuild (delete + recreate +
# reinstall) via reset_virtual_environments.sh when they differ.
rebuild_stale_venvs() {
    local current
    current=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null) || return 0
    local cfg venv_version
    for cfg in /opt/wrolpi/venv/pyvenv.cfg \
               /opt/wrolpi/controller/venv/pyvenv.cfg \
               /opt/wrolpi-help/venv/pyvenv.cfg; do
        [ -r "${cfg}" ] || continue
        # pyvenv.cfg records e.g. "version = 3.11.2"; match that key exactly so
        # the newer "version_info = ..." line is ignored.  Reduce to major.minor.
        venv_version=$(awk -F'=' '$1 ~ /^[[:space:]]*version[[:space:]]*$/ {gsub(/[[:space:]]/,"",$2); print $2; exit}' "${cfg}")
        venv_version=${venv_version%.*}
        if [ -n "${venv_version}" ] && [ "${venv_version}" != "${current}" ]; then
            echo "Python changed (venv at ${cfg%/pyvenv.cfg} built for ${venv_version}, system is now ${current}); rebuilding all virtual environments..."
            /opt/wrolpi/scripts/reset_virtual_environments.sh -y
            return 0
        fi
    done
}

rebuild_stale_venvs
# ---------------------------------------------------------------------------

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
    DENO_VERSION="v2.8.3"
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

# Upgrade single-file to the pinned version; old versions (1.x) create compressed Archives without
# the SingleFile comment header in the prelude, which WROLPi cannot validate.
# readability-extractor is pinned alongside it to match the install scripts.
upgrade_singlefile() {
    SINGLE_FILE_VERSION="2.0.73"
    if [ "$(single-file --version 2>/dev/null)" != "${SINGLE_FILE_VERSION}" ]; then
        echo "Upgrading single-file-cli to ${SINGLE_FILE_VERSION}..."
        npm i -g single-file-cli@${SINGLE_FILE_VERSION} readability-extractor@0.0.6
    else
        echo "single-file-cli ${SINGLE_FILE_VERSION} already installed"
    fi
}

upgrade_singlefile || echo "single-file upgrade failed, continuing..."

# Clear Python bytecode cache before upgrading packages.
echo "Clearing Python bytecode cache..."
find /opt/wrolpi/venv -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || :
find /opt/wrolpi/venv -name "*.pyc" -delete 2>/dev/null || :

# Install any new Python requirements.
/opt/wrolpi/venv/bin/pip3 install --upgrade -r /opt/wrolpi/requirements.txt
# Upgrade the WROLPi database.  Never fatal: the media drive may not be mounted;
# the API creates/migrates the database itself at startup once the media directory is available.
(cd /opt/wrolpi && /opt/wrolpi/venv/bin/python3 /opt/wrolpi/main.py db upgrade) || \
  echo "WARNING: db upgrade failed (media directory unavailable?); the API will retry at startup."

# WROLPi now uses SQLite (inside the media directory); stop and disable PostgreSQL to free
# system resources on upgrades from older installs.  The old Postgres data is NOT deleted --
# to get it back temporarily: sudo systemctl enable --now postgresql
# To reclaim disk later: sudo apt-get remove --purge postgresql*
if id postgres >/dev/null 2>&1; then
  echo "Disabling PostgreSQL; WROLPi now uses SQLite.  Your old Postgres data is untouched."
  # Stop the umbrella and any per-cluster instances (postgresql@15-main, etc.).
  systemctl stop 'postgresql*' 2>/dev/null || :
  systemctl disable postgresql 2>/dev/null || :
fi
# Remove legacy Postgres client credentials (no longer used).
rm -f /home/wrolpi/.pgpass

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

# Finish configuring any package left half-configured by an interrupted apt/dpkg run
# (e.g. a prior upgrade that died at a conffile prompt).
DEBIAN_FRONTEND=noninteractive dpkg --force-confdef --force-confold --configure -a || :

# Migrate from nginx to Caddy if necessary.
if ! command -v caddy &>/dev/null; then
  echo "Installing Caddy (replacing nginx)..."
  # Disable and stop nginx if it was previously used.
  systemctl stop nginx 2>/dev/null || :
  systemctl disable nginx 2>/dev/null || :
  # Install Caddy from official apt repo.
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  # Non-interactive: a conffile prompt (e.g. repair.sh already wrote /etc/caddy/Caddyfile)
  # would otherwise hang or abort under the tty-less wrolpi-upgrade.service.
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold caddy
fi

# Install Samba if not already installed.
if ! command -v smbd &>/dev/null; then
  echo "Installing Samba..."
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold samba
fi

# Install gnome-disk-utility if not already installed (provides desktop disk management GUI).
if ! command -v gnome-disks &>/dev/null; then
  echo "Installing gnome-disk-utility..."
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold gnome-disk-utility
fi

# Install dnsmasq-base if not already installed (NetworkManager needs it for the hotspot's
# DHCP; it is only a Recommends of network-manager, so ISOs built with --apt-recommends
# false shipped without it).  iw and rfkill are WiFi diagnostic tools.
if ! command -v dnsmasq &>/dev/null || ! command -v iw &>/dev/null || ! command -v rfkill &>/dev/null; then
  echo "Installing dnsmasq-base, iw, rfkill..."
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold dnsmasq-base iw rfkill
fi

# Clean up stale landing page (Controller now serves port 80 directly).
rm -f /var/www/landing.html

# Install any configs, restart services.
/opt/wrolpi/repair.sh
