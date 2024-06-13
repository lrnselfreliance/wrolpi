# This Dockerfile is used as a reverse proxy to serve a HTTPS nieve service with HTTPS.
FROM nginx:latest as https_proxy

# Create a self-signed cert and key pair for HTTPS.
RUN openssl genrsa -out /cert.key 2048
RUN openssl req -new -x509 -nodes -key /cert.key -out /cert.crt -days 3650  \
    -subj "/C=US/ST=State/L=City/O=Org/OU=WROLPi/CN=wrolpi.local"
RUN chmod 777 /cert.key /cert.crt

# Copy Nginx configuration
COPY docker/https_proxy/nginx.proxy.conf /etc/nginx/nginx.conf
CMD ["nginx", "-g", "daemon off;"]
