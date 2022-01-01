"""Archive contents search.

Revision ID: 31896cc29b71
Revises: bddb5e95a91e
Create Date: 2021-12-31 18:53:25.326674

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '31896cc29b71'
down_revision = 'bddb5e95a91e'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE archive ADD COLUMN contents TEXT')
    session.execute('''
        ALTER TABLE archive
        ADD COLUMN textsearch tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english'::regconfig, title), 'A') ||
            setweight(to_tsvector('english'::regconfig, contents), 'D')
        ) STORED
    ''')
    session.execute('CREATE INDEX IF NOT EXISTS archive_textsearch_idx ON archive USING GIN(textsearch)')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('DROP INDEX IF EXISTS archive_textsearch_idx')
    session.execute('ALTER TABLE archive DROP COLUMN IF EXISTS contents')
    session.execute('ALTER TABLE archive DROP COLUMN IF EXISTS textsearch')
