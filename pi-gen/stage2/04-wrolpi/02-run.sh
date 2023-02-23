#! /bin/bash -e
mkdir -p "${ROOTFS_DIR}/opt/wrolpi-blobs"

cp files/district-of-columbia-*.dump.gz "${ROOTFS_DIR}/opt/wrolpi-blobs/gis-map.dump.gz"

set +x

echo
echo "======================================================================"
echo "02-run.sh completed"
echo "======================================================================"
echo
