#!/usr/bin/env bash
echo "Debian install start: $(date '+%Y-%m-%d %H:%M:%S')"

set -x
set -e

# Run the install in a predictable UTF-8 locale.  Fresh images (or SSH sessions
# forwarding LC_* variables from the client) may reference an ungenerated
# locale, which makes apt/perl/python emit "Cannot set LC_CTYPE" warnings
# throughout the install.  C.UTF-8 is built into glibc, always present, and
# locale-neutral, so this does not change the user's configured locale.
export LC_ALL=C.UTF-8

# Update if we haven't updated in the last day.
[ -z "$(find -H /var/lib/apt/lists -maxdepth 0 -mtime -1)" ] && apt update
# Install dependencies.
apt-get install -y $(cat /opt/wrolpi/debian-live-config/config/package-lists/wrolpi.list.chroot)

# App dependencies were installed.
node -v
npm -v

# Install serve and the archiving tools from the committed lockfile.
/opt/wrolpi/scripts/install_npm_tools.sh

# Install Deno runtime; single-file runs under it.
command -v deno || {
  DENO_VERSION="v2.8.3"
  ARCH=$(uname -m)
  if [ "$ARCH" = "aarch64" ]; then
    DENO_ARCH="aarch64-unknown-linux-gnu"
    DENO_SHA256="d4589cc1ffcbf1995c92a0127d932aaf832ac70cfdcc6d5b7bf38043cf303575"
  else
    DENO_ARCH="x86_64-unknown-linux-gnu"
    DENO_SHA256="30455b845ffa6082209c3590269c910ad3b7efdf28c9879afd4006c47ae54197"
  fi
  curl -fsSL "https://github.com/denoland/deno/releases/download/${DENO_VERSION}/deno-${DENO_ARCH}.zip" -o /tmp/deno.zip
  # Assert the hash to avoid malicious or invalid files.
  echo "${DENO_SHA256}  /tmp/deno.zip" | sha256sum -c -
  unzip -o /tmp/deno.zip -d /usr/local/bin/
  chmod +x /usr/local/bin/deno
  rm /tmp/deno.zip
}
deno --version

# Build React app in background job.
cd /opt/wrolpi/app || exit 5
npm install || npm install || npm install || npm install # try install multiple times  :(

# Install python requirements in background job.
python3 -m venv /opt/wrolpi/venv
/opt/wrolpi/venv/bin/pip3 install --upgrade -r /opt/wrolpi/requirements.txt

# Create the Controller venv (kept separate from the main API venv).
python3 -m venv /opt/wrolpi/controller/venv
/opt/wrolpi/controller/venv/bin/pip3 install --upgrade -r /opt/wrolpi/controller/requirements.txt

# Create the WROLPi user
grep wrolpi: /etc/passwd || useradd -md /home/wrolpi wrolpi -s "$(command -v bash)"

# Install Caddy from official apt repo if not already installed.
if ! command -v caddy &>/dev/null; then
  /opt/wrolpi/scripts/add_caddy_apt_repo.sh
  apt-get update
  apt-get install -y caddy
fi

# Install WROLPi Help.
/opt/wrolpi/scripts/install_help_service.sh

# Repair will install configs and restart services.
/opt/wrolpi/repair.sh

set +x

echo "

WROLPi has successfully been installed!

Browse to http://$(hostname).local to choose the drive for your library, or join
the WiFi hotspot:
SSID: WROLPi
Password: wrolpi hotspot

"
