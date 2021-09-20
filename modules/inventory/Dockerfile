FROM python:3.9
ENV DOCKER=true

WORKDIR /opt/wrolpi

# Install dependencies
COPY main.py /opt/wrolpi/
COPY config /opt/wrolpi/config
COPY wrolpi /opt/wrolpi/wrolpi
RUN pip install -r /opt/wrolpi/wrolpi/requirements.txt
RUN mkdir /opt/wrolpi/services
RUN touch /opt/wrolpi/services/__init__.py

# Copy this service.
COPY inventory /opt/wrolpi/services/inventory
RUN pip install -r /opt/wrolpi/services/inventory/requirements.txt

ENTRYPOINT [ "python3", "/opt/wrolpi/main.py"]
CMD ["api", "--host", "0.0.0.0" ]
