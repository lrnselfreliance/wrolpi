FROM postgres:12
ENV POSTGRES_DB wrolpi
COPY lib/plugins/*/sql/* /docker-entrypoint-initdb.d/
