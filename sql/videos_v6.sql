-- This column was never used.
ALTER TABLE video DROP COLUMN name;

-- This is the length of the video in seconds.
ALTER TABLE video ADD COLUMN duration INT;
