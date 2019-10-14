-- noinspection SqlNoDataSourceInspectionForFile

DROP TABLE IF EXISTS channel;
CREATE TABLE channel
(
    id          SERIAL PRIMARY KEY,
    name        TEXT,
    link        TEXT,
    idempotency TEXT,
    url         TEXT,
    match_regex TEXT,
    directory   TEXT,
    info_json   JSON,
    info_date   DATE
);

DROP TABLE IF EXISTS video;
CREATE TABLE video
(
    id               SERIAL PRIMARY KEY,
    description_path TEXT,
    ext              TEXT,
    poster_path      TEXT,
    source_id        TEXT,
    title            TEXT,
    upload_date      DATE,
    video_path       TEXT,
    name             TEXT,
    caption_path     TEXT,
    idempotency      TEXT,
    info_json_path   TEXT,
    video_path_hash  TEXT
);

ALTER TABLE video
    ADD COLUMN channel_id INTEGER REFERENCES channel (id);
