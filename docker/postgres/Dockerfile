FROM postgres:12
ENV POSTGRES_DB wrolpi
COPY wrolpi/plugins/*/sql/* /docker-entrypoint-initdb.d/
