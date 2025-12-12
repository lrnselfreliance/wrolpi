FROM python:3.11-slim

LABEL maintainer="WROLPi"
LABEL description="WROLPi Controller Service"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY controller/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy Controller code
COPY controller/ /app/controller/

# Environment
ENV PYTHONUNBUFFERED=1
ENV DOCKERIZED=true

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8087/api/health || exit 1

EXPOSE 8087

CMD ["uvicorn", "controller.main:app", "--host", "0.0.0.0", "--port", "8087"]
