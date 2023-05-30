FROM debian:12
ENV DOCKER=true

RUN apt update && apt-get install -y kiwix kiwix-tools
COPY docker/zim/* /

ENTRYPOINT ["/entrypoint.sh"]