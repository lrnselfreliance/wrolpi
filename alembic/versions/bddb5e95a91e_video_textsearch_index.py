"""Video textsearch index

Revision ID: bddb5e95a91e
Revises: db0a1560d923
Create Date: 2021-12-31 18:12:00.407694

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'bddb5e95a91e'
down_revision = 'db0a1560d923'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('DROP INDEX IF EXISTS video_textsearch_idx')
    session.execute('ALTER TABLE video DROP COLUMN IF EXISTS textsearch')
    session.execute('''
        ALTER TABLE video
        ADD COLUMN textsearch tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english'::regconfig, title), 'A') ||
            setweight(to_tsvector('english'::regconfig, caption), 'B')
        ) STORED
    ''')
    session.execute('CREATE INDEX IF NOT EXISTS video_textsearch_idx ON video USING GIN(textsearch)')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('DROP INDEX IF EXISTS video_textsearch_idx')
    session.execute("""
        ALTER TABLE video
        ADD COLUMN IF NOT EXISTS textsearch tsvector
        GENERATED ALWAYS AS (to_tsvector('english'::regconfig,
                           ((COALESCE(title, ''::text) || ' '::text) ||
                            COALESCE(caption, ''::text)))) STORED
    """)
