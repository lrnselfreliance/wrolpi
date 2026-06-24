FROM python:3.11-bookworm
ENV DOCKER=true
WORKDIR /opt/wrolpi

# Update dependencies for the services install.
RUN apt-get update && apt-get install -y ffmpeg catdoc sysstat aria2 iputils-ping unrar-free unzip \
    build-essential libsqlite3-dev zlib1g-dev git

# Install tippecanoe (for map search index building via tippecanoe-decode).
RUN git clone --depth 1 --branch 2.79.0 https://github.com/felt/tippecanoe.git /tmp/tippecanoe \
    && cd /tmp/tippecanoe && make -j$(nproc) && make install \
    && rm -rf /tmp/tippecanoe \
    && tippecanoe-decode --help 2>&1 | head -1
RUN ffmpeg -version

# Install Deno runtime for yt-dlp.  yt-dlp's EJS challenge solver requires Deno >=2.3.0; pin
# v2.8.3 to match scripts/upgrade.sh and docker/archive/Dockerfile.
RUN DENO_VERSION="v2.8.3" \
    && ARCH=$(uname -m) \
    && if [ "$ARCH" = "aarch64" ]; then \
         DENO_ARCH="aarch64-unknown-linux-gnu"; \
         DENO_SHA256="d4589cc1ffcbf1995c92a0127d932aaf832ac70cfdcc6d5b7bf38043cf303575"; \
       elif [ "$ARCH" = "x86_64" ]; then \
         DENO_ARCH="x86_64-unknown-linux-gnu"; \
         DENO_SHA256="30455b845ffa6082209c3590269c910ad3b7efdf28c9879afd4006c47ae54197"; \
       else echo "Unsupported architecture: $ARCH" && exit 1; fi \
    && curl -fsSL "https://github.com/denoland/deno/releases/download/${DENO_VERSION}/deno-${DENO_ARCH}.zip" -o /tmp/deno.zip \
    # Assert the hash to avoid malicious or invalid files.
    && echo "${DENO_SHA256}  /tmp/deno.zip" | sha256sum -c - \
    && unzip -o /tmp/deno.zip -d /usr/local/bin/ \
    && chmod +x /usr/local/bin/deno \
    && rm /tmp/deno.zip \
    && deno --version

# yt-dlp needs cache directory
RUN mkdir /.cache && chown -R 1000:1000 /.cache

# Install dependencies.
COPY requirements.txt /opt/wrolpi/requirements.txt
RUN pip3 install -r /opt/wrolpi/requirements.txt

# Install WROLPi.
COPY main.py /opt/wrolpi/
COPY wrolpi /opt/wrolpi/wrolpi
COPY modules /opt/wrolpi/modules

ENTRYPOINT [ "python3", "/opt/wrolpi/main.py"]
# Log level controlled by LOG_LEVEL env var or wrolpi.yaml config (default: info)
CMD ["api", "--host", "0.0.0.0"]
