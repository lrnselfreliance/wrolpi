FROM python:3.11-bookworm
ENV DOCKER=true
WORKDIR /opt/wrolpi-help

# Copy application files.
COPY docker/help/wrolpi-help /opt/wrolpi-help

# Install dependencies.
RUN pip3 install --no-cache-dir -r /opt/wrolpi-help/requirements.txt

# Serve MkDocs documentation.
ENTRYPOINT ["mkdocs"]
CMD ["serve", "-a", "0.0.0.0:8086"]