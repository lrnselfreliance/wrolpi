#! /usr/bin/env bash
# Build the default fallback Zim that Kiwix serves when a WROLPi has no
# functioning Zim files.  The output is committed to wrolpi/blobs/default.zim,
# which every build copies into /opt/wrolpi-blobs.
#
# Reproducible via the openzim/zim-tools Docker image, so no host zim-tools
# installation is required.  Re-run this only when src/ changes.
set -euo pipefail

HERE="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &>/dev/null && pwd )"
BLOBS="$( cd -- "${HERE}/../../blobs" &>/dev/null && pwd )"
# Pinned (not :latest) so the committed default.zim is reproducible: identical
# source assets always build with the same zimwriterfs release.
IMAGE="ghcr.io/openzim/zim-tools:3.7.0"

echo "Building default.zim from ${HERE}/src -> ${BLOBS}/default.zim ..."
rm -f "${BLOBS}/default.zim"  # zimwriterfs refuses to overwrite an existing file.
docker run --rm -v "${HERE}:/work" -v "${BLOBS}:/out" -w /work "${IMAGE}" \
  zimwriterfs \
    --welcome=index.html \
    --illustration=favicon.png \
    --language=eng \
    --title="WROLPi" \
    --description="Default WROLPi Zim. Download Zim files to replace this placeholder." \
    --creator="WROLPi" \
    --publisher="WROLPi" \
    --name="wrolpi.default" \
    src /out/default.zim

echo "Validating default.zim ..."
docker run --rm -v "${BLOBS}:/out" -w /out "${IMAGE}" zimcheck default.zim

echo "Done: ${BLOBS}/default.zim"
