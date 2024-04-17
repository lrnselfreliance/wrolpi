FROM python:3.11-buster
ENV DOCKER=true
WORKDIR /opt/wrolpi

# Update dependencies for the services install.
RUN apt update
# ffmpeg for Videos
RUN apt-get install -y ffmpeg catdoc
RUN ffmpeg -version

# Install dependencies.
COPY requirements.txt /opt/wrolpi/requirements.txt
RUN pip3 install -r /opt/wrolpi/requirements.txt

# Install WROLPi.
COPY main.py /opt/wrolpi/
COPY wrolpi /opt/wrolpi/wrolpi
COPY modules /opt/wrolpi/modules

ENTRYPOINT [ "python3", "-OO", "/opt/wrolpi/main.py"]
CMD ["-vv", "api", "--host", "0.0.0.0"]
