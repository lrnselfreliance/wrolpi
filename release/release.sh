#!/bin/bash
# Build, checksum, upload, and publish a WROLPi release.
#
# Runs the full release pipeline as a single command:
#   1. Resolve the version from the target git ref (branch or tag).
#   2. Build the amd64 ISO (debian-live-config) and aarch64 image (pi-gen).
#   3. Generate .sha256 sidecars.
#   4. Upload images + checksums to DigitalOcean Spaces (s3cmd).
#   5. Publish latest.json (the manifest wrolpi.org reads) to the bucket root.
#
# Everything here talks only to public endpoints (github.com, the Spaces CDN).
# Spaces credentials live in the s3cmd config (~/.s3cfg or $S3CFG), never here.
#
#   sudo ./release.sh                 # build the 'release' branch
#   sudo ./release.sh -b v0.23.0-beta # build a specific tag
#   ./release.sh -b release -n        # dry run: build nothing, show upload plan
#
# Building a tag works because the chroot hooks `git clone -b <ref>`, which
# accepts a tag (detached HEAD) just as well as a branch.

set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
REPO_DIR=$( cd -- "${SCRIPT_DIR}/.." &> /dev/null && pwd )

# Public constants.  None of these are secret; the bucket and CDN host are
# already visible on wrolpi.org.
REPO="lrnselfreliance/wrolpi"
BUCKET="s3://wrolpi"
CDN_BASE="https://wrolpi.nyc3.cdn.digitaloceanspaces.com"
# Cache the manifest briefly so a new release shows up quickly; cache the
# immutable versioned images for a year.
MANIFEST_CACHE="public, max-age=300"
IMAGE_CACHE="public, max-age=31536000, immutable"
# How many times to attempt each upload before giving up.  Spaces occasionally
# returns a transient 400 mid-multipart on the multi-GB images, so a single
# failed part should not doom an otherwise-good multi-hour build.
UPLOAD_RETRIES=3

REF="release"
DRY_RUN=0

Help() {
  echo "Build and publish a WROLPi release."
  echo
  echo "Syntax: release.sh [-h] [-b REF] [-n]"
  echo "options:"
  echo "h     Print this help."
  echo "b     Build from this git branch or tag (default: 'release')."
  echo "n     Dry run: skip the build and only print the upload/manifest plan."
  echo
}

while getopts ":hb:n" option; do
  case $option in
  h) Help; exit ;;
  b) REF="${OPTARG}" ;;
  n) DRY_RUN=1 ;;
  *) echo "Error: Invalid option"; Help; exit 1 ;;
  esac
done

# s3cmd reads $S3CFG if set (handy when this runs as root via systemd but the
# credentials live in a user's home), otherwise its default ~/.s3cfg.
S3CMD=(s3cmd)
[ -n "${S3CFG:-}" ] && S3CMD=(s3cmd -c "${S3CFG}")

log() { echo "[release] $*"; }
die() { echo "[release] ERROR: $*" >&2; exit 1; }

# Optional completion hook.  Set WROLPI_RELEASE_NOTIFY to a command that accepts
# a single message argument; it is invoked on success and on failure.  Unset by
# default, so this public script names no notifier and no path.
notify() {
  [ -n "${WROLPI_RELEASE_NOTIFY:-}" ] || return 0
  "${WROLPI_RELEASE_NOTIFY}" "$1" || true
}

# Report the outcome via the notify hook (skipped for dry runs).  Installed
# only after the version resolves, so help/early-exit paths stay silent.
on_exit() {
  local rc=$?
  [ "${DRY_RUN}" -eq 1 ] && return
  if [ "${rc}" -eq 0 ]; then
    notify "WROLPi v${VERSION} released -- ${CDN_BASE}/latest.json"
  else
    notify "WROLPi release FAILED (exit ${rc}) for v${VERSION:-?}"
  fi
}

# Resolve the version straight from the target ref so the artifact names match
# the code that gets built.
VERSION=$(curl -fsSL "https://raw.githubusercontent.com/${REPO}/${REF}/wrolpi/version.txt" | tr -d '[:space:]')
[ -n "${VERSION}" ] || die "Could not fetch version from ref '${REF}'"
log "Releasing WROLPi v${VERSION} (ref: ${REF})"
trap on_exit EXIT

ISO="${REPO_DIR}/debian-live-config/WROLPi-v${VERSION}-amd64.iso"
IMG="${REPO_DIR}/pi-gen/WROLPi-v${VERSION}-aarch64-desktop.img.xz"

if [ "${DRY_RUN}" -eq 1 ]; then
  log "DRY RUN: skipping builds."
else
  log "Building amd64 ISO..."
  "${REPO_DIR}/debian-live-config/build.sh" -b "${REF}"
  log "Building aarch64 image..."
  "${REPO_DIR}/pi-gen/build.sh" -b "${REF}"
  [ -s "${ISO}" ] || die "Expected ISO not found: ${ISO}"
  [ -s "${IMG}" ] || die "Expected image not found: ${IMG}"
fi

# Compute checksum + size for the manifest.  In a dry run the artifacts may not
# exist, so fall back to placeholders.
checksum() { [ -s "$1" ] && sha256sum "$1" | cut -d' ' -f1 || echo "DRYRUN"; }
bytesize() { [ -s "$1" ] && stat -c%s "$1" || echo 0; }

ISO_SHA=$(checksum "${ISO}")
IMG_SHA=$(checksum "${IMG}")
ISO_SIZE=$(bytesize "${ISO}")
IMG_SIZE=$(bytesize "${IMG}")

# Write .sha256 sidecars next to the artifacts (standard `sha256sum` format).
if [ "${DRY_RUN}" -eq 0 ]; then
  ( cd "$(dirname "${ISO}")" && sha256sum "$(basename "${ISO}")" > "${ISO}.sha256" )
  ( cd "$(dirname "${IMG}")" && sha256sum "$(basename "${IMG}")" > "${IMG}.sha256" )
fi

ISO_NAME=$(basename "${ISO}")
IMG_NAME=$(basename "${IMG}")
RELEASED=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Build latest.json.  jq -n keeps the values properly escaped/typed.
# `.tag` is the git ref that was built: a release tag for automated builds
# (release-watch.sh compares it to decide what is already published) or a
# branch name for manual runs.  Use `.version` for a display version.
MANIFEST=$(jq -n \
  --arg version "${VERSION}" \
  --arg tag "${REF}" \
  --arg released "${RELEASED}" \
  --arg cdn "${CDN_BASE}" \
  --arg iso_name "${ISO_NAME}" --arg iso_sha "${ISO_SHA}" --argjson iso_size "${ISO_SIZE}" \
  --arg img_name "${IMG_NAME}" --arg img_sha "${IMG_SHA}" --argjson img_size "${IMG_SIZE}" \
  '{
    version: $version,
    tag: $tag,
    released: $released,
    downloads: [
      { key: "desktop", title: "Raspberry Pi", arch: "aarch64",
        filename: $img_name, url: ($cdn + "/" + $img_name),
        sha256_url: ($cdn + "/" + $img_name + ".sha256"),
        sha256: $img_sha, size: $img_size },
      { key: "debian", title: "Debian", arch: "amd64",
        filename: $iso_name, url: ($cdn + "/" + $iso_name),
        sha256_url: ($cdn + "/" + $iso_name + ".sha256"),
        sha256: $iso_sha, size: $iso_size }
    ]
  }')

MANIFEST_FILE="${SCRIPT_DIR}/latest.json"
echo "${MANIFEST}" > "${MANIFEST_FILE}"

# Abort any in-progress multipart upload for a key.  A failed multi-GB upload
# leaves orphaned parts behind that incur storage cost and can interfere with a
# clean retry, so we clear them before re-attempting.  Small files never use
# multipart, so this is a harmless no-op for them.
abort_multipart() {
  local name="$1"
  "${S3CMD[@]}" multipart "${BUCKET}" 2>/dev/null \
    | awk -v k="${BUCKET}/${name}" '$2 == k { print $3 }' \
    | while read -r id; do
        [ -n "${id}" ] && "${S3CMD[@]}" abortmp "${BUCKET}/${name}" "${id}" >/dev/null 2>&1 || true
      done
}

put() {
  # put <local> <mime> <cache-control>
  local src="$1" mime="$2" cache="$3"
  local name; name=$(basename "${src}")
  if [ "${DRY_RUN}" -eq 1 ]; then
    log "DRY RUN would upload: ${name}  (${mime})"
    return
  fi
  local attempt
  for attempt in $(seq 1 "${UPLOAD_RETRIES}"); do
    if "${S3CMD[@]}" put --acl-public --no-progress \
        --mime-type="${mime}" \
        --add-header="Cache-Control:${cache}" \
        "${src}" "${BUCKET}/${name}"; then
      return 0
    fi
    log "Upload of ${name} failed (attempt ${attempt}/${UPLOAD_RETRIES})."
    # Clear any partial multipart upload before retrying, then back off briefly.
    abort_multipart "${name}"
    [ "${attempt}" -lt "${UPLOAD_RETRIES}" ] && sleep 5
  done
  die "Upload of ${name} failed after ${UPLOAD_RETRIES} attempts."
}

log "Uploading artifacts to ${BUCKET}..."
put "${ISO}"        "application/x-iso9660-image" "${IMAGE_CACHE}"
put "${ISO}.sha256" "text/plain"                  "${IMAGE_CACHE}"
put "${IMG}"        "application/x-xz"            "${IMAGE_CACHE}"
put "${IMG}.sha256" "text/plain"                  "${IMAGE_CACHE}"

log "Publishing manifest..."
put "${MANIFEST_FILE}" "application/json" "${MANIFEST_CACHE}"

log "Done. Published v${VERSION}:"
log "  ${CDN_BASE}/${ISO_NAME}"
log "  ${CDN_BASE}/${IMG_NAME}"
log "  ${CDN_BASE}/latest.json"
