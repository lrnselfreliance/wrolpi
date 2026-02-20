FROM python:3.11-bookworm
ENV DOCKER=true
WORKDIR /opt/wrolpi

# Update dependencies for the services install.
RUN apt-get update && apt-get install -y ffmpeg catdoc sysstat aria2 iputils-ping unzip
RUN ffmpeg -version

# Install Deno runtime for yt-dlp
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "aarch64" ]; then DENO_ARCH="aarch64-unknown-linux-gnu"; \
    elif [ "$ARCH" = "x86_64" ]; then DENO_ARCH="x86_64-unknown-linux-gnu"; \
    else echo "Unsupported architecture: $ARCH" && exit 1; fi && \
    curl -fsSL "https://github.com/denoland/deno/releases/download/v2.2.4/deno-${DENO_ARCH}.zip" -o /tmp/deno.zip \
    && unzip /tmp/deno.zip -d /usr/local/bin/ \
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
