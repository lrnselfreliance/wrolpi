FROM python:3.9
ENV DOCKER=true

WORKDIR /opt/wrolpi

# Install dependencies
RUN apt update
RUN apt install -y chromium

# Copy minimum directories/files
COPY main.py config *local.yaml alembic.ini /opt/wrolpi/
COPY api /opt/wrolpi/api

# Install all requirements files.
COPY requirements.txt /opt/wrolpi/
RUN find -name requirements.txt -exec pip install --upgrade -r {} \;

# Setup the wrolpi user
RUN useradd -d /opt/wrolpi wrolpi
RUN chown -R wrolpi:wrolpi /opt/wrolpi
USER wrolpi

# Run the webserver
ENTRYPOINT [ "python3", "/opt/wrolpi/main.py"]
CMD ["archive", "--host", "0.0.0.0" ]
