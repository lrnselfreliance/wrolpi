"""Initialize with channel, video, inventory, and item.

Revision ID: 7cb1a9eb38b5
Revises:
Create Date: 2021-06-18 14:48:20.746548

"""
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '7cb1a9eb38b5'
down_revision = None
branch_labels = None
depends_on = None


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
    validated_poster BOOLEAN DEFAULT false
)''')

    session.execute('''CREATE TABLE public.inventory
(
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    viewed_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITHOUT TIME ZONE
)''')

    session.execute('''CREATE TABLE public.item
(
    id SERIAL PRIMARY KEY,
    inventory_id INTEGER REFERENCES inventory(id) ON DELETE CASCADE,
    brand TEXT,
    name TEXT,
    count DECIMAL,
    item_size DECIMAL,
    unit TEXT,
    serving INTEGER,
    category TEXT,
    subcategory TEXT,
    expiration_date DATE,
    purchase_date DATE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITHOUT TIME ZONE
)''')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP TABLE IF EXISTS channel CASCADE')
    session.execute('DROP TABLE IF EXISTS video CASCADE')
    session.execute('DROP TABLE IF EXISTS item CASCADE')
    session.execute('DROP TABLE IF EXISTS inventory CASCADE')
