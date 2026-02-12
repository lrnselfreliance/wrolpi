#!/bin/bash
set -e
set -x

# Preseed debconf answers to avoid interactive prompts during package installation.
# iperf3 asks whether to start as a daemon at boot - answer yes since we enable it via systemctl.
echo "iperf3 iperf3/start_daemon boolean true" | debconf-set-selections

set +x

echo
echo "======================================================================"
echo "00-run-chroot.sh completed"
echo "======================================================================"
echo
