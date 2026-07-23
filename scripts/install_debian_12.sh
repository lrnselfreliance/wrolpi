#!/usr/bin/env bash
echo "Debian 12 install start: $(date '+%Y-%m-%d %H:%M:%S')"

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

# Install serve, and archiving tools.
single-file --version || sudo npm i -g serve@12.0.1 single-file-cli@2.0.73 readability-extractor@0.0.6

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
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
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

Mount your external hard drive to /media/wrolpi if you have one.  Change the
file permissions if necessary:
 # sudo chown -R wrolpi:wrolpi /media/wrolpi

Start the WROLPi services using:
 # sudo systemctl start wrolpi.target

then navigate to:  https://$(hostnmae).local

Or, join to the Wifi hotspot:
SSID: WROLPi
Password: wrolpi hotspot

"
