FROM nginx:alpine
WORKDIR /etc/nginx

# Generate self-signed certificate and key.
RUN apk add --no-cache openssl && \
    openssl genrsa -out /cert.key 2048 && \
    openssl req -new -x509 -nodes -key /cert.key -out /cert.crt -days 3650 \
        -subj "/C=US/ST=State/L=City/O=Org/OU=WROLPi/CN=wrolpi.local" && \
    chmod 600 /cert.key /cert.crt && \
    apk del openssl

# Remove default Nginx config.
RUN rm /etc/nginx/conf.d/default.conf

# Copy Nginx configuration and assets.
COPY docker/web/nginx.dev.conf /etc/nginx/nginx.conf
COPY docker/web/wrolpi.dev.conf /etc/nginx/conf.d/wrolpi.conf
COPY icon.ico icon.png /etc/nginx/

# Run Nginx in foreground.
CMD ["nginx", "-g", "daemon off;"]