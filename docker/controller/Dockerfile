FROM python:3.13-slim-trixie

LABEL maintainer="WROLPi"
LABEL description="WROLPi Controller Service"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching; installed from the hash-locked requirements.
COPY controller/requirements.txt controller/requirements.lock /app/
COPY scripts/install_python_requirements.sh /app/install_python_requirements.sh
RUN PIP_NO_CACHE_DIR=1 /app/install_python_requirements.sh pip /app/requirements.txt

# Copy Controller code
COPY controller/ /app/controller/

# Environment
ENV PYTHONUNBUFFERED=1
ENV DOCKERIZED=true

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:80/api/health || exit 1

EXPOSE 80

CMD ["python", "-m", "controller.serve"]
