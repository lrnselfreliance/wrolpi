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
    session.execute('CREATE INDEX IF NOT EXISTS video_textsearch_idx ON video USING GIN(textsearch)')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('DROP INDEX IF EXISTS video_textsearch_idx')
