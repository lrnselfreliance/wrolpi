FROM debian:12-slim
ENV DOCKER=true
WORKDIR /app

# Install kiwix and kiwix-tools.
RUN apt-get update && \
    apt-get install -y kiwix kiwix-tools && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy entrypoint script and make it executable.
COPY docker/zim/* /
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]