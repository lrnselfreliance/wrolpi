ALTER TABLE video DROP CONSTRAINT video_channel_id_fkey;
ALTER TABLE video ADD CONSTRAINT video_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES channel(id) ON DELETE CASCADE;