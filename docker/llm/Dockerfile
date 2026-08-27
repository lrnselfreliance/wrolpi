FROM debian:13
ENV DOCKER=true

RUN apt-get update && apt-get install -y curl ca-certificates

# Build llama-server from the pinned release (single source of truth with native installs).
COPY wrolpi/scripts/install_llama_cpp.sh /tmp/install_llama_cpp.sh
RUN /tmp/install_llama_cpp.sh && rm /tmp/install_llama_cpp.sh \
    && apt-get remove -y build-essential cmake && apt-get autoremove -y \
    # llama-server needs the OpenMP runtime, which the build-tool cleanup just removed.
    && apt-get install -y libgomp1 && apt-get clean

# The same startup scripts the native install uses.
COPY scripts/start_llama_server.sh /opt/wrolpi/scripts/start_llama_server.sh
COPY wrolpi/scripts/read_config_value.sh /opt/wrolpi/wrolpi/scripts/read_config_value.sh

COPY docker/llm/entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
