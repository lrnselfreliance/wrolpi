FROM python:3.9
ENV DOCKER=true

WORKDIR /opt/wrolpi

# Update dependencies for the services install.
RUN apt update

# Install dependencies
COPY main.py /opt/wrolpi/
COPY config /opt/wrolpi/config
COPY wrolpi /opt/wrolpi/wrolpi
COPY modules /opt/wrolpi/modules
RUN pip install -r /opt/wrolpi/wrolpi/requirements.txt

# Install the services
RUN find /opt/wrolpi/modules -name 'install.sh' -exec {} \;
RUN find /opt/wrolpi/modules -name 'requirements.txt' -exec pip install -r {} \;

ENTRYPOINT [ "python3", "/opt/wrolpi/main.py"]
CMD ["api", "--host", "0.0.0.0" ]
