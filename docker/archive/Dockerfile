FROM capsulecode/singlefile

USER root
WORKDIR /app

# Install Python for main.py
ENV PYTHONUNBUFFERED=1
RUN apk add --update --no-cache python3 python3-dev && ln -sf python3 /usr/bin/python
RUN python3 -m ensurepip
RUN pip3 install --no-cache --upgrade pip setuptools

# Install the Python wrapper and it's requirements.
COPY docker/archive /app
RUN pip3 install -r /app/requirements.txt

# Install Readability too
RUN npm install -g 'git+https://github.com/pirate/readability-extractor'

# Block ads using /etc/hosts
RUN wget https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts -O /etc/hosts

ENTRYPOINT [ "python3", "/app/main.py"]
