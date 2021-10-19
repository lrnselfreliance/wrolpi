FROM python:3.9-buster
ENV DOCKER=true
WORKDIR /opt/wrolpi

# Update dependencies for the services install.
RUN apt update
RUN apt install -y ffmpeg wkhtmltopdf

# Install WROLPi
COPY main.py /opt/wrolpi/
COPY config /opt/wrolpi/config
COPY wrolpi /opt/wrolpi/wrolpi
COPY modules /opt/wrolpi/modules
# Remove archive, its not for this service.
RUN pip3 install -r /opt/wrolpi/wrolpi/requirements.txt
RUN find /opt/wrolpi/modules -name 'requirements.txt' -exec pip3 install -r {} \;

ENTRYPOINT [ "python3", "/opt/wrolpi/main.py"]
CMD ["api", "--host", "0.0.0.0" ]
