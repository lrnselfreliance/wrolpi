"""Archive textsearch coalesce fix.

Revision ID: 62acddc55091
Revises: 0400005fe2dc
Create Date: 2022-01-04 11:11:29.100317

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '62acddc55091'
down_revision = '0400005fe2dc'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('DROP INDEX IF EXISTS archive_textsearch_idx')
    session.execute('ALTER TABLE archive DROP COLUMN IF EXISTS textsearch')
    session.execute('''
        ALTER TABLE archive
        ADD COLUMN textsearch tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english'::regconfig, COALESCE(title, '')), 'A') ||
            setweight(to_tsvector('english'::regconfig, COALESCE(contents, '')), 'D')
        ) STORED
    ''')
    session.execute('CREATE INDEX archive_textsearch_idx ON archive USING GIN(textsearch)')


def downgrade():
    # The upgrade is backwards compatible.
    pass
