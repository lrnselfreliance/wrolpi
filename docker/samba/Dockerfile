FROM debian:12-slim
RUN apt-get update && \
    apt-get install -y --no-install-recommends samba samba-common && \
    rm -rf /var/lib/apt/lists/*
EXPOSE 445
CMD ["smbd", "--foreground", "--no-process-group", "--debug-stdout", "-s", "/media/wrolpi/config/smb.conf"]
