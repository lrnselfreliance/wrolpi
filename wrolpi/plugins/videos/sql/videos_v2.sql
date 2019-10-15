-- Captions will be stored as a tsvector for searching
ALTER TABLE video
    ADD COLUMN caption TEXT;

-- Combine (and index) the title and captions for natural language searching
ALTER TABLE video
    ADD COLUMN textsearch TSVECTOR
        GENERATED ALWAYS AS (
            to_tsvector('english', COALESCE (title, '') || ' ' || COALESCE (caption, ''))
            ) STORED;
CREATE INDEX textsearch_idx ON video USING GIN (textsearch);
