FROM nginx:latest

# Create a self-signed cert and key pair for HTTPS.
RUN openssl genrsa -out /cert.key 2048
RUN openssl req -new -x509 -nodes -key /cert.key -out /cert.crt -days 3650  \
    -subj "/C=US/ST=State/L=City/O=Org/OU=WROLPi/CN=wrolpi.local"
RUN chmod 777 /cert.key /cert.crt
