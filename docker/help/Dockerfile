FROM python:3.11-bookworm
ENV DOCKER=true
WORKDIR /opt/wrolpi-help

COPY docker/help/wrolpi-help /opt/wrolpi-help
RUN pip3 install -r /opt/wrolpi-help/requirements.txt

ENTRYPOINT ["mkdocs"]
CMD ["serve", "-a", "0.0.0.0:80"]
