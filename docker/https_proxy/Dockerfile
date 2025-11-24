# This Dockerfile is used as a reverse proxy to serve a HTTPS nieve service with HTTPS.
FROM nginx:latest AS https_proxy

# Create a self-signed cert and key pair for HTTPS.
RUN openssl genrsa -out /cert.key 2048
RUN openssl req -new -x509 -nodes -key /cert.key -out /cert.crt -days 3650  \
    -subj "/C=US/ST=State/L=City/O=Org/OU=WROLPi/CN=wrolpi.local"
RUN chmod 777 /cert.key /cert.crt

# Apply docker-compose environment variables to config
ENV UPSTREAM_HOST=you-must-change-this-in-docker-compose
ENV UPSTREAM_PORT=80
COPY docker/https_proxy/nginx.proxy.conf.template /etc/nginx/nginx.conf
RUN envsubst < /etc/nginx/nginx.conf > /etc/nginx/nginx.conf

CMD ["nginx", "-g", "daemon off;"]
