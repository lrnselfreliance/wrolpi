#! /bin/bash -e
mkdir -p "${ROOTFS_DIR}/opt/wrolpi-blobs"

cp files/* "${ROOTFS_DIR}/opt/wrolpi-blobs/"

set +x

echo
echo "======================================================================"
echo "02-run.sh completed"
echo "======================================================================"
echo
