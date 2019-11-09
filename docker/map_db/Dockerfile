FROM kartoza/postgis:10.0-2.4

ENV POSTGRES_USER=renderaccount
ENV POSTGRES_DBNAME=gis
ENV DEFAULT_ENCODING="UTF8"
ENV DEFAULT_COLLATION="en_US.UTF-8"
ENV DEFAULT_CTYPE="en_US.UTF-8"

RUN sudo -iu postgres psql gis postgres -c 'CREATE EXTENSION postgis; CREATE EXTENSION hstore; ALTER TABLE ' \
  'geometry_columns OWNER TO renderaccount; ALTER TABLE spatial_ref_sys OWNER TO renderaccount;'
