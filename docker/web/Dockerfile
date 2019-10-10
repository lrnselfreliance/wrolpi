FROM python:3.7-buster

# Setup a python virtualenv
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib/

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the main script as well as the WROLPi directory
WORKDIR /opt/wrolpi
CMD [ "python3", "/opt/wrolpi/main.py", "-v", "web", "--host", "0.0.0.0" ]
