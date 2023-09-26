#!/usr/bin/env bash
# Shared bash scripting functionality. This is not meant to be run by itself.

function yes_or_no {
  while true; do
    read -p "$* [y/n]:" yn
    case $yn in
    [Yy]*) return 0 ;;
    [Nn]*) return 1 ;;
    esac
  done
}

# The full path to the WROLPi project directory (typically "/opt/wrolpi")
PROJECT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
PROJECT_DIR=$(dirname "${PROJECT_DIR}")
PROJECT_DIR=$(dirname "${PROJECT_DIR}")

rpi=false
debian12=false
if (grep 'Raspberry Pi' /proc/cpuinfo >/dev/null); then
  rpi=true
fi
if (grep 'PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"' /etc/os-release >/dev/null); then
  debian12=true
fi

if [[ ${rpi} == false && ${debian12} == false ]]; then
  echo 'This script can only be run on a Raspberry Pi or Debian 12!' && exit 2
fi
