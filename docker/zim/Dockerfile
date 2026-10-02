FROM debian:13
ENV DOCKER=true

# curl is for the compose healthcheck.
RUN apt update && apt-get install -y kiwix kiwix-tools curl

# Committed blobs (e.g. the default Zim served when the media directory has no
# functioning zim files).
COPY wrolpi/blobs/ /opt/wrolpi-blobs/

COPY docker/zim/* /

ENTRYPOINT ["/entrypoint.sh"]