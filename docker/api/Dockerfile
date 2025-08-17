FROM python:3.11-bookworm
ENV DOCKER=true
WORKDIR /opt/wrolpi

# Update dependencies for the services install.
RUN apt-get update && apt-get install -y ffmpeg catdoc sysstat aria2 iputils-ping
RUN ffmpeg -version
# yt-dlp needs cache directory
RUN mkdir /.cache && chown -R 1000:1000 /.cache

# Install dependencies.
COPY requirements.txt /opt/wrolpi/requirements.txt
RUN pip3 install -r /opt/wrolpi/requirements.txt

# Install WROLPi.
COPY main.py /opt/wrolpi/
COPY wrolpi /opt/wrolpi/wrolpi
COPY modules /opt/wrolpi/modules

ENTRYPOINT [ "python3", "-OO", "/opt/wrolpi/main.py"]
CMD ["-v", "api", "--host", "0.0.0.0"]
