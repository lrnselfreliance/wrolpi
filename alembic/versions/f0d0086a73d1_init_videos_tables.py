"""Init videos tables.

Revision ID: f0d0086a73d1
Revises:
Create Date: 2021-09-20 16:19:36.576217

"""
from alembic import op
from sqlalchemy.orm import Session

revision = 'f0d0086a73d1'
down_revision = None
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''CREATE TABLE public.channel
(
    id BIGSERIAL PRIMARY KEY,
    name TEXT,
    link TEXT UNIQUE,
    idempotency TEXT,
    url TEXT,
    match_regex TEXT,
    directory TEXT,
    info_json JSON,
    info_date DATE,
    skip_download_videos text[],
    generate_posters BOOLEAN DEFAULT true,
    calculate_duration BOOLEAN DEFAULT true,
    download_frequency INTEGER,
    next_download DATE
)''')

    session.execute('''CREATE TABLE public.video
(
    id BIGSERIAL PRIMARY KEY,
    title TEXT,
    ext TEXT,
    source_id TEXT,
    description_path TEXT,
    poster_path TEXT,
    video_path TEXT,
    caption_path TEXT,
    info_json_path TEXT,
    idempotency TEXT,
    channel_id INTEGER REFERENCES channel(id) ON DELETE CASCADE,
    caption TEXT,
    textsearch tsvector GENERATED ALWAYS AS (to_tsvector('english'::regconfig,
                                               ((COALESCE(title, ''::text) || ' '::text) ||
                                                COALESCE(caption, ''::text)))) STORED,
    upload_date TIMESTAMP WITHOUT TIME ZONE,
    duration INTEGER,
    favorite TIMESTAMP WITHOUT TIME ZONE,
    size BIGINT,
    viewed TIMESTAMP WITHOUT TIME ZONE,
    validated_poster BOOLEAN DEFAULT false,
    view_count INTEGER
)''')

    if not DOCKERIZED:
        session.execute('ALTER TABLE public.channel OWNER TO wrolpi')
        session.execute('ALTER TABLE public.video OWNER TO wrolpi')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP TABLE IF EXISTS channel CASCADE')
    session.execute('DROP TABLE IF EXISTS video CASCADE')
