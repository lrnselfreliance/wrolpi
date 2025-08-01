FROM python:3.11-buster
ENV DOCKER=true
WORKDIR /opt/wrolpi

# Update dependencies and install required packages
RUN apt-get update && \
    apt-get install -y ffmpeg catdoc sysstat aria2 postgresql-client && \
    ffmpeg -version && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create cache directory for yt-dlp
RUN mkdir /.cache && chown -R 1000:1000 /.cache

# Install Python dependencies
COPY requirements.txt /opt/wrolpi/requirements.txt
RUN pip3 install --no-cache-dir -r /opt/wrolpi/requirements.txt

# Copy WROLPi application files
COPY main.py /opt/wrolpi/
COPY wrolpi /opt/wrolpi/wrolpi
COPY modules /opt/wrolpi/modules
COPY alembic /opt/wrolpi/alembic
COPY docker/api/alembic.ini /opt/wrolpi/alembic.ini

# Copy and set up entrypoint script
COPY docker/api/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Use entrypoint script which will run alembic migrations before starting API.
ENTRYPOINT ["/entrypoint.sh"]