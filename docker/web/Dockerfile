FROM python:3.8

# Setup a python virtualenv
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib/

# Copy minimal directories/files
COPY main.py /opt/wrolpi/main.py
COPY requirements.txt /opt/wrolpi/requirements.txt
COPY wrolpi /opt/wrolpi/wrolpi
# Install dependencies
RUN ls -laR /opt/wrolpi
RUN find /opt/wrolpi -name requirements.txt -exec pip install --upgrade -r {} \;

# Run the webserver
WORKDIR /opt/wrolpi
CMD [ "python3", "/opt/wrolpi/main.py", "-v", "web", "--host", "0.0.0.0" ]
