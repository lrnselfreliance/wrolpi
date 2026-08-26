#! /usr/bin/env bash
# Bind all interfaces so the api container can reach llama-server on the internal docker network.
# The container publishes no host ports and is not proxied by Caddy.
export LLAMA_HOST=0.0.0.0
exec /opt/wrolpi/scripts/start_llama_server.sh
