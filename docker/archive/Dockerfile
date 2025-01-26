FROM browserless/chrome:1.61.1-chrome-stable

USER root
WORKDIR /app

# Install Python for main.py
ENV PYTHONUNBUFFERED=1
RUN apt update && apt install -y python3 python3-dev python3-venv curl && ln -sf python3 /usr/bin/python
RUN python3 -m venv /app/venv
RUN . /app/venv/bin/activate

# Install a newer singlefile and Readability.
RUN npm install -g single-file-cli@2.0.73 readability-extractor@0.0.6

# Install the Python wrapper and it's requirements.
COPY docker/archive/requirements.txt /app/requirements.txt
RUN  /app/venv/bin/pip3 install -r /app/requirements.txt
COPY docker/archive /app

# Launch Archive app in the virtual environment.
ENTRYPOINT [ "/app/venv/bin/python3", "/app/main.py"]
