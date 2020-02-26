ALTER TABLE video
    DROP COLUMN downloaded;
ALTER TABLE video
    ADD CONSTRAINT video_channel_id_source_id_unique UNIQUE (channel_id, source_id);
