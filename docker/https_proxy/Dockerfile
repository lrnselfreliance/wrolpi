# docker/https_proxy/Dockerfile
FROM nginx:latest AS https_proxy
WORKDIR /etc/nginx

ARG UPSTREAM_HOST
ARG UPSTREAM_PORT=80

# Generate self-signed certificate and key
RUN openssl genrsa -out /cert.key 2048
RUN openssl req -new -x509 -nodes -key /cert.key -out /cert.crt -days 3650 \
    -subj "/C=US/ST=State/L=City/O=Org/OU=${UPSTREAM_HOST}/CN=wrolpi.local"
RUN chmod 600 /cert.key /cert.crt

# Define downstream host for each *_https container.
COPY docker/https_proxy/nginx.proxy.conf.template /etc/nginx/nginx.conf
RUN sed -ie "s/UPSTREAM_HOST/$UPSTREAM_HOST/" nginx.conf && \
    sed -ie "s/UPSTREAM_PORT/$UPSTREAM_PORT/" nginx.conf

CMD ["nginx", "-g", "daemon off;"]