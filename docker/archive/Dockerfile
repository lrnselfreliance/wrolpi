# Keep older singlefile version so we can keep screenshots at specific ratio.
FROM capsulecode/singlefile:v0.3.32

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

# Install a newer singlefile and Readability.
RUN npm install -g single-file-cli@2.0.34 readability-extractor@0.0.6

ENTRYPOINT [ "python3", "/app/main.py"]
