FROM browserless/chrome:1.61.1-chrome-stable
WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Switch to root for package installation
USER root

# Install Python and dependencies
RUN apt-get update && \
    apt-get install -y python3 python3-dev python3-venv curl && \
    ln -sf python3 /usr/bin/python && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set up virtual environment
RUN python3 -m venv /app/venv

# Install Node.js dependencies
RUN npm install -g single-file-cli@2.0.73 readability-extractor@0.0.6

# Install Python dependencies
COPY docker/archive/requirements.txt /app/requirements.txt
RUN /app/venv/bin/pip3 install --no-cache-dir -r /app/requirements.txt

# Copy application files
COPY docker/archive/main.py /app/

# Launch Archive app in virtual environment
ENTRYPOINT ["/app/venv/bin/python3", "/app/main.py"]