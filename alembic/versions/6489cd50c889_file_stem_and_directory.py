"""File stem and directory

Revision ID: 6489cd50c889
Revises: 13542a230c78
Create Date: 2022-12-04 15:39:55.485355

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '6489cd50c889'
down_revision = '13542a230c78'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE file ADD COLUMN directory TEXT')
    session.execute('ALTER TABLE file ADD COLUMN full_stem TEXT')
    session.execute('ALTER TABLE file ADD COLUMN stem TEXT')
    session.execute('CREATE INDEX file_directory_idx ON file(directory)')
    session.execute('CREATE INDEX file_full_stem_idx ON file(full_stem)')
    session.execute('CREATE INDEX file_stem_idx ON file(stem)')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP INDEX IF EXISTS file_directory_idx')
    session.execute('DROP INDEX IF EXISTS file_full_stem_idx')
    session.execute('DROP INDEX IF EXISTS file_stem_idx')
    session.execute('ALTER TABLE file DROP COLUMN IF EXISTS directory')
    session.execute('ALTER TABLE file DROP COLUMN IF EXISTS full_stem')
    session.execute('ALTER TABLE file DROP COLUMN IF EXISTS stem')
