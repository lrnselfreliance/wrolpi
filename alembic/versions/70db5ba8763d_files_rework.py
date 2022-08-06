"""Files rework.  Unifying files for Videos and Archives.

Revision ID: 70db5ba8763d
Revises: aac864072193
Create Date: 2022-07-27 20:11:30.990396

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '70db5ba8763d'
down_revision = 'aac864072193'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    # Recreate the file table.  Use file.path as the primary key.
    session.execute('DROP TABLE IF EXISTS file')
    session.execute('''CREATE TABLE file (
        path TEXT PRIMARY KEY,
        idempotency TIMESTAMP WITH TIME ZONE,
        indexed BOOLEAN DEFAULT FALSE,
        mimetype TEXT,
        suffix TEXT,
        model TEXT,
        associated BOOLEAN DEFAULT FALSE,
        modification_datetime TIMESTAMP WITH TIME ZONE,
        size BIGINT,
        title TEXT,
        a_text TEXT,
        b_text TEXT,
        c_text TEXT,
        d_text TEXT,
        textsearch tsvector GENERATED ALWAYS AS (
            setweight(to_tsvector('english'::regconfig, COALESCE(a_text, '')), 'A'::"char") ||
            setweight(to_tsvector('english'::regconfig, COALESCE(b_text, '')), 'B'::"char") ||
            setweight(to_tsvector('english'::regconfig, COALESCE(c_text, '')), 'C'::"char") ||
            setweight(to_tsvector('english'::regconfig, COALESCE(d_text, '')), 'D'::"char")
        ) STORED
    )''')
    session.execute('CREATE INDEX file_mimetype_idx ON file USING BTREE(mimetype)')
    session.execute('CREATE INDEX file_textsearch_idx ON file USING GIN(textsearch)')
    session.execute('CREATE INDEX file_modification_datetime_idx ON file USING BTREE(modification_datetime)')
    session.execute('CREATE INDEX file_size_idx ON file USING BTREE(size)')
    session.execute('CREATE INDEX file_model_idx ON file USING BTREE(model)')
    session.execute('CREATE INDEX file_idempotency_idx ON file USING BTREE(idempotency)')
    session.execute('CREATE INDEX file_suffix_idx ON file USING BTREE(suffix)')

    # Videos are fundamentally different, replace the video table.
    session.execute('DROP TABLE IF EXISTS video')
    session.execute('''
    CREATE TABLE video (
        id BIGSERIAL PRIMARY KEY,
        title TEXT,
        source_id TEXT,
        channel_id INTEGER REFERENCES channel(id),
        upload_date TIMESTAMPTZ,
        duration INTEGER,
        favorite TIMESTAMPTZ,
        size BIGINT,
        viewed TIMESTAMPTZ,
        view_count INTEGER,
        url TEXT,
        censored BOOLEAN DEFAULT FALSE,
        validated BOOLEAN DEFAULT FALSE,
        modification_datetime TIMESTAMPTZ,
        video_path TEXT REFERENCES file(path),
        info_json_path TEXT REFERENCES file(path),
        poster_path TEXT REFERENCES file(path),
        caption_path TEXT REFERENCES file(path)
    )''')
    session.execute('''
    CREATE INDEX video_caption_path_idx ON video(caption_path);
    CREATE INDEX video_info_json_path_idx ON video(info_json_path);
    CREATE INDEX video_poster_path_idx ON video(poster_path);
    CREATE INDEX video_video_path_idx ON video(video_path);
    CREATE INDEX video_url_idx ON video(url);
    ''')

    session.execute('ALTER TABLE channel DROP COLUMN IF EXISTS idempotency')

    session.execute('DELETE FROM archive')  # noqa
    session.execute('DELETE FROM domains')  # noqa
    session.execute('DROP TABLE IF EXISTS archive')
    session.execute('DROP TABLE IF EXISTS domains')
    session.execute('''
    CREATE TABLE domains (
        id SERIAL PRIMARY KEY,
        domain TEXT NOT NULL,
        directory TEXT
    )''')
    session.execute('''
    CREATE TABLE archive (
        id SERIAL PRIMARY KEY,
        domain_id INTEGER REFERENCES domains(id),
        title TEXT,
        archive_datetime timestamptz,
        url TEXT,
        validated BOOLEAN DEFAULT FALSE,
        singlefile_path TEXT REFERENCES file(path),
        readability_path TEXT REFERENCES file(path),
        readability_json_path TEXT REFERENCES file(path),
        readability_txt_path TEXT REFERENCES file(path),
        screenshot_path TEXT REFERENCES file(path)
    )''')
    session.execute('''
    CREATE INDEX archive_singlefile_path ON archive(singlefile_path);
    CREATE INDEX archive_readability_path ON archive(readability_path);
    CREATE INDEX archive_readability_json_path ON archive(readability_json_path);
    CREATE INDEX archive_readability_txt_path ON archive(readability_txt_path);
    CREATE INDEX archive_screenshot_path ON archive(screenshot_path);
    ''')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''
    DROP INDEX IF EXISTS archive_singlefile_path;
    DROP INDEX IF EXISTS archive_readability_path;
    DROP INDEX IF EXISTS archive_readability_json_path;
    DROP INDEX IF EXISTS archive_readability_txt_path;
    DROP INDEX IF EXISTS archive_screenshot_path;
    ''')

    session.execute('DELETE FROM archive')  # noqa
    session.execute('''
    ALTER TABLE archive DROP COLUMN IF EXISTS singlefile_path;
    ALTER TABLE archive DROP COLUMN IF EXISTS readability_path;
    ALTER TABLE archive DROP COLUMN IF EXISTS readability_json_path;
    ALTER TABLE archive DROP COLUMN IF EXISTS readability_txt_path;
    ALTER TABLE archive DROP COLUMN IF EXISTS screenshot_path;
    ALTER TABLE archive DROP COLUMN IF EXISTS associated;
    ''')
    session.execute('''
    ALTER TABLE archive ADD COLUMN IF NOT EXISTS singlefile_path TEXT;
    ALTER TABLE archive ADD COLUMN IF NOT EXISTS readability_path TEXT;
    ALTER TABLE archive ADD COLUMN IF NOT EXISTS readability_json_path TEXT;
    ALTER TABLE archive ADD COLUMN IF NOT EXISTS readability_txt_path TEXT;
    ALTER TABLE archive ADD COLUMN IF NOT EXISTS screenshot_path TEXT;
    ALTER TABLE archive ADD COLUMN IF NOT EXISTS contents TEXT;
    ALTER TABLE archive ADD COLUMN IF NOT EXISTS status TEXT;
    ''')
    session.execute('ALTER TABLE archive ALTER COLUMN domain_id SET NOT NULL')

    session.execute('ALTER TABLE channel ADD COLUMN IF NOT EXISTS idempotency TEXT')

    session.execute('DELETE FROM video')  # noqa
    session.execute('''
    ALTER TABLE video DROP COLUMN IF EXISTS caption_path;
    ALTER TABLE video DROP COLUMN IF EXISTS info_json_path;
    ALTER TABLE video DROP COLUMN IF EXISTS poster_path;
    ALTER TABLE video DROP COLUMN IF EXISTS video_path;
    ALTER TABLE video DROP COLUMN IF EXISTS video_path;
    ''')
    session.execute('''
    ALTER TABLE video ADD COLUMN IF NOT EXISTS idempotency TEXT;
    ALTER TABLE video ADD COLUMN IF NOT EXISTS caption_path TEXT;
    ALTER TABLE video ADD COLUMN IF NOT EXISTS description_path TEXT;
    ALTER TABLE video ADD COLUMN IF NOT EXISTS info_json_path TEXT;
    ALTER TABLE video ADD COLUMN IF NOT EXISTS poster_path TEXT;
    ALTER TABLE video ADD COLUMN IF NOT EXISTS video_path TEXT;
    ALTER TABLE video ADD COLUMN IF NOT EXISTS caption TEXT;
    ''')
    session.execute('''
    DROP INDEX IF EXISTS video_caption_path_idx;
    DROP INDEX IF EXISTS video_info_json_path_idx;
    DROP INDEX IF EXISTS video_poster_path_idx;
    DROP INDEX IF EXISTS video_video_path_idx;
    DROP INDEX IF EXISTS video_url_idx;
    ''')
    session.execute('''
        ALTER TABLE video
        ADD COLUMN textsearch tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english'::regconfig, title), 'A') ||
            setweight(to_tsvector('english'::regconfig, caption), 'D')
        ) STORED
    ''')
    session.execute('CREATE INDEX IF NOT EXISTS video_textsearch_idx ON video USING GIN(textsearch)')

    session.execute('DROP INDEX IF EXISTS file_mimetype_idx')
    session.execute('DROP INDEX IF EXISTS file_textsearch_idx')
    session.execute('DROP INDEX IF EXISTS file_modification_datetime_idx')
    session.execute('DROP INDEX IF EXISTS file_size_idx')
    session.execute('DROP INDEX IF EXISTS file_model_idx')
    session.execute('DROP INDEX IF EXISTS file_idempotency_idx')
    session.execute('DROP INDEX IF EXISTS file_suffix_idx')

    # Restore the old file table.
    session.execute('DROP TABLE IF EXISTS file')
    session.execute('''CREATE TABLE file (
        id SERIAL PRIMARY KEY,
        path TEXT,
        title TEXT,
        mimetype TEXT,
        size BIGINT,
        modification_datetime TIMESTAMP WITH TIME ZONE,
        idempotency TEXT DEFAULT NULL,
        textsearch tsvector GENERATED ALWAYS AS (
            setweight(to_tsvector('english'::regconfig, title), 'A'::"char")
        ) STORED
    )''')
    session.execute('CREATE UNIQUE INDEX file_path_idx ON file USING BTREE(path)')
    session.execute('CREATE INDEX file_mimetype_idx ON file USING BTREE(mimetype)')
    session.execute('CREATE INDEX file_textsearch_idx ON file USING GIN(textsearch)')
