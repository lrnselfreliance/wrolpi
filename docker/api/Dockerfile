FROM python:3.8
ENV DOCKER=true

# Copy minimal directories/files
COPY main.py requirements.txt example.yaml *local.yaml /opt/wrolpi/
COPY lib /opt/wrolpi/lib
# Install dependencies
RUN find /opt/wrolpi -name requirements.txt -exec pip install --upgrade -q -r {} \;

# Run the webserver
WORKDIR /opt/wrolpi
CMD [ "python3", "/opt/wrolpi/main.py", "-vv", "api", "--host", "0.0.0.0" ]
