"""Video textsearch coalesce fix.

Revision ID: 0400005fe2dc
Revises: 53f6780aa599
Create Date: 2022-01-04 11:00:21.776124

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '0400005fe2dc'
down_revision = '53f6780aa599'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    # Replace the textsearch and index.  The old textsearch failed if one of the columns was null.
    session.execute('DROP INDEX IF EXISTS video_textsearch_idx')
    session.execute('ALTER TABLE video DROP COLUMN IF EXISTS textsearch')
    session.execute('''
        ALTER TABLE video
        ADD COLUMN textsearch tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english'::regconfig, COALESCE(title, '')), 'A') ||
            setweight(to_tsvector('english'::regconfig, COALESCE(caption, '')), 'D')
        ) STORED
    ''')
    session.execute('CREATE INDEX video_textsearch_idx ON video USING GIN(textsearch)')


def downgrade():
    # The upgrade is backwards compatible.
    pass
