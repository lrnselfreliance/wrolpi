#! /bin/bash -e
mkdir -p "${ROOTFS_DIR}/opt/wrolpi-blobs"

cp files/district-of-columbia-230111.dump.gz "${ROOTFS_DIR}/opt/wrolpi-blobs/gis-map.dump.gz"
