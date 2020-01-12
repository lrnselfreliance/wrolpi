FROM python:3.8
ENV DOCKER=true

WORKDIR /opt/wrolpi

# Install dependencies
COPY requirements.txt /opt/wrolpi/
RUN find -name requirements.txt -exec pip install --upgrade -q -r {} \;

# Copy minimal directories/files
COPY main.py example.yaml *local.yaml /opt/wrolpi/
COPY api /opt/wrolpi/api

# Run the webserver
ENTRYPOINT [ "python3", "/opt/wrolpi/main.py"]
CMD ["api", "--host", "0.0.0.0" ]
