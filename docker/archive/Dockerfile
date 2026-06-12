FROM browserless/chrome:1.61.1-chrome-stable

USER root
WORKDIR /app

# Install Python for main.py
ENV PYTHONUNBUFFERED=1
RUN apt update && apt install -y python3 python3-dev python3-venv curl unzip && ln -sf python3 /usr/bin/python
RUN python3 -m venv /app/venv
RUN . /app/venv/bin/activate

# Install a newer singlefile and Readability.
RUN npm install -g single-file-cli@2.0.73 readability-extractor@0.0.6

# Install Deno; single-file-cli is designed for it (under node 18 it cannot reach the browser CDP
# on IPv6-enabled hosts and never exits).  Match the version pinned in scripts/upgrade.sh.
RUN DENO_VERSION="v2.8.3" \
    && ARCH=$(uname -m) \
    && if [ "$ARCH" = "aarch64" ]; then \
         DENO_ARCH="aarch64-unknown-linux-gnu"; \
         DENO_SHA256="d4589cc1ffcbf1995c92a0127d932aaf832ac70cfdcc6d5b7bf38043cf303575"; \
       else \
         DENO_ARCH="x86_64-unknown-linux-gnu"; \
         DENO_SHA256="30455b845ffa6082209c3590269c910ad3b7efdf28c9879afd4006c47ae54197"; \
       fi \
    && curl -fsSL "https://github.com/denoland/deno/releases/download/${DENO_VERSION}/deno-${DENO_ARCH}.zip" -o /tmp/deno.zip \
    # Assert the hash to avoid malicious or invalid files.
    && echo "${DENO_SHA256}  /tmp/deno.zip" | sha256sum -c - \
    && unzip -o /tmp/deno.zip -d /usr/local/bin/ \
    && chmod +x /usr/local/bin/deno \
    && rm /tmp/deno.zip \
    && deno --version

# Install the Python wrapper and it's requirements.
COPY docker/archive/requirements.txt /app/requirements.txt
RUN  /app/venv/bin/pip3 install -r /app/requirements.txt
COPY docker/archive /app
COPY scripts/singlefile_browser_wrapper.sh /app/singlefile_browser_wrapper.sh

# Launch Archive app in the virtual environment.
ENTRYPOINT [ "/app/venv/bin/python3", "/app/main.py"]
