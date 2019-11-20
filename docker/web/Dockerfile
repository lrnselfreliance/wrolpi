FROM python:3.8
ENV DOCKER=true

# Copy minimal directories/files
COPY requirements.txt /opt/wrolpi/
COPY lib /opt/wrolpi/lib
# Install dependencies
RUN find /opt/wrolpi -name requirements.txt -exec pip install --upgrade -r {} \;

# Run the webserver
WORKDIR /opt/wrolpi
CMD [ "python3", "/opt/wrolpi/main.py", "-v", "web", "--host", "0.0.0.0" ]
