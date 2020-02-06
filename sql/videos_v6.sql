-- This column was never used.
ALTER TABLE video DROP COLUMN name;

-- This is the length of the video in seconds.
ALTER TABLE video ADD COLUMN length_seconds INT;
-- This will be True if WROLPi generates a poster for a video.
ALTER TABLE video ADD COLUMN generated_poster BOOL DEFAULT FALSE;
