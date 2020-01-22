-- Convert upload_date to a Timestamp column, preserving data.
ALTER TABLE video ADD COLUMN upload_date_2 TIMESTAMP;
UPDATE video SET upload_date_2 = upload_date;
ALTER TABLE video DROP COLUMN upload_date;
ALTER TABLE video RENAME COLUMN upload_date_2 TO upload_date;

-- Add "downloaded" column to video so we can speed up downloading videos
ALTER TABLE video ADD COLUMN downloaded BOOLEAN DEFAULT FALSE;
