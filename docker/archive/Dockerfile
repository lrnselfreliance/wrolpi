FROM capsulecode/singlefile

USER root
WORKDIR /app

# Install Python for main.py
ENV PYTHONUNBUFFERED=1
RUN apk add --update --no-cache python3 python3-dev curl && ln -sf python3 /usr/bin/python
RUN python3 -m ensurepip
RUN pip3 install --no-cache --upgrade pip setuptools

# Install the Python wrapper and it's requirements.
COPY docker/archive/requirements.txt /app/requirements.txt
RUN pip3 install -r /app/requirements.txt
COPY docker/archive /app

# Install Readability too
RUN npm install -g 'git+https://github.com/pirate/readability-extractor'

ENTRYPOINT [ "python3", "/app/main.py"]
