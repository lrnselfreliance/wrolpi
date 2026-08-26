#! /usr/bin/env bash
# Start llama-server (WROLPi's local AI inference runtime) with the model selected in ai.yaml.
#
# AI is opt-in: this refuses to start unless ai.yaml enables it and the active model file exists
# in the media directory (which also covers the unmounted-media case).  Started/stopped on demand
# by the Controller; the API's idle-unload worker stops it after inactivity.
set -u

MEDIA_DIRECTORY="${MEDIA_DIRECTORY:-/media/wrolpi}"
PROJECT_DIR="${PROJECT_DIR:-/opt/wrolpi}"
AI_CONFIG="${MEDIA_DIRECTORY}/config/ai.yaml"
# Docker overrides the host so the api container can reach this container.
LLAMA_HOST="${LLAMA_HOST:-127.0.0.1}"
LLAMA_PORT="${LLAMA_PORT:-11435}"

read_ai_config() {
  MEDIA_DIRECTORY="${MEDIA_DIRECTORY}" WROLPI_CONFIG_FILE="${AI_CONFIG}" \
    "${PROJECT_DIR}/wrolpi/scripts/read_config_value.sh" "$@"
}

[ ! -d "${MEDIA_DIRECTORY}" ] && echo "Cannot start llama-server without media directory mounted" && exit 1
[ ! -f "${AI_CONFIG}" ] && echo "Cannot start llama-server without ${AI_CONFIG}" && exit 1

ENABLED="$(read_ai_config enabled false)"
if [ "${ENABLED}" != "true" ] && [ "${ENABLED}" != "True" ]; then
  echo "AI is not enabled in ${AI_CONFIG}; refusing to start"
  exit 1
fi

ACTIVE_MODEL="$(read_ai_config active_model)"
[ -z "${ACTIVE_MODEL}" ] && echo "No active_model in ${AI_CONFIG}; refusing to start" && exit 1
# Defense in depth: the model must be a bare file name inside the models directory.
case "${ACTIVE_MODEL}" in
  */*|*..*)
    echo "Ignoring unsafe active_model '${ACTIVE_MODEL}'" >&2
    exit 1
    ;;
esac
MODEL="${MEDIA_DIRECTORY}/ai/models/${ACTIVE_MODEL}"
[ ! -f "${MODEL}" ] && echo "Model file does not exist: ${MODEL}" && exit 1

CONTEXT_SIZE="$(read_ai_config context_size 8192)"
case "${CONTEXT_SIZE}" in
  ''|*[!0-9]*) CONTEXT_SIZE=8192 ;;
esac

# --jinja enables tool-call chat templates; mmap is llama.cpp's default so cold RAM cost is low.
# Localhost only on native installs -- never exposed through Caddy.
exec llama-server \
  --host "${LLAMA_HOST}" \
  --port "${LLAMA_PORT}" \
  --jinja \
  -c "${CONTEXT_SIZE}" \
  -m "${MODEL}"
