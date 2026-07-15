#!/usr/bin/env bash
# Install WROLPi's map toolchain: the pmtiles CLI (a prebuilt Go binary) and
# tippecanoe (compiled from source, used to build map search indexes).
#
# This is the single source of truth, called by every place that provisions a
# WROLPi so a version bump only has to be made here:
#   - scripts/install_protomaps.sh                        (on-device upgrade)
#   - pi-gen/stage2/04-wrolpi/03-run-chroot.sh            (Raspberry Pi image build)
#   - debian-live-config/config/hooks/normal/9999-wrolpi.hook.chroot  (Debian Live ISO build)
#
# Baking the tools into an image and running this again on-device stay
# consistent because each installer is version-guarded: a tool already at the
# pinned version is left untouched, so on-device runs are no-ops until the
# pinned version actually changes.  Upstream artifacts are SHA-pinned to detect
# tampering.  Run as root: installs into /usr/local/bin and apt-installs build
# dependencies.
set -e

PMTILES_VERSION="v1.30.1"
# Per-arch SHA256 of the Linux release tarballs (go-pmtiles ships prebuilt binaries).
PMTILES_SHA256_amd64="23a2a2222f658320b539ccd06ac3b9b3b803ecbdd39a6cb5249d2ce2e16e38ae"
PMTILES_SHA256_arm64="a1f9f42d8317ab1fadc25dd050e208547f32a3f99a4b90e7cb8fd6030f143d8e"

TIPPECANOE_VERSION="2.79.0"
# SHA256 of the *source* tarball -- arch-independent, so one value covers every build.
TIPPECANOE_SHA256="b0fd9df49b6efc988288ea48774822c6de19eb48428017f27ee0b3b01d44f05d"

install_pmtiles() {
  local arch sha
  case "$(uname -m)" in
    aarch64) arch="arm64"; sha="${PMTILES_SHA256_arm64}" ;;
    x86_64) arch="amd64"; sha="${PMTILES_SHA256_amd64}" ;;
    *) echo "Unsupported architecture for pmtiles: $(uname -m)"; return 1 ;;
  esac

  if command -v pmtiles &>/dev/null; then
    local current
    current=$(pmtiles version 2>&1 | head -1 | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' || echo "")
    if [ "${current}" = "${PMTILES_VERSION}" ]; then
      echo "pmtiles ${PMTILES_VERSION} already installed"
      return 0
    fi
  fi

  echo "Installing pmtiles ${PMTILES_VERSION} (${arch})..."
  curl -fsSL "https://github.com/protomaps/go-pmtiles/releases/download/${PMTILES_VERSION}/go-pmtiles_${PMTILES_VERSION#v}_Linux_${arch}.tar.gz" \
    -o /tmp/pmtiles.tar.gz
  echo "${sha}  /tmp/pmtiles.tar.gz" | sha256sum -c -
  tar -xz -C /usr/local/bin/ -f /tmp/pmtiles.tar.gz pmtiles
  rm -f /tmp/pmtiles.tar.gz
  chmod +x /usr/local/bin/pmtiles
  pmtiles version
}

install_tippecanoe() {
  if command -v tippecanoe-decode &>/dev/null; then
    local current
    current=$(tippecanoe --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "")
    if [ "${current}" = "${TIPPECANOE_VERSION}" ]; then
      echo "tippecanoe ${TIPPECANOE_VERSION} already installed"
      return 0
    fi
  fi

  echo "Building tippecanoe ${TIPPECANOE_VERSION}..."
  apt-get install -y build-essential libsqlite3-dev zlib1g-dev

  local build_dir
  build_dir=$(mktemp -d)
  curl -fsSL "https://github.com/felt/tippecanoe/archive/refs/tags/${TIPPECANOE_VERSION}.tar.gz" \
    -o /tmp/tippecanoe.tar.gz
  echo "${TIPPECANOE_SHA256}  /tmp/tippecanoe.tar.gz" | sha256sum -c -
  tar -xz -C "${build_dir}" --strip-components=1 -f /tmp/tippecanoe.tar.gz
  rm -f /tmp/tippecanoe.tar.gz
  (cd "${build_dir}" && make -j"$(nproc)" && make install)
  rm -rf "${build_dir}"
  tippecanoe --version
}

install_pmtiles
install_tippecanoe
