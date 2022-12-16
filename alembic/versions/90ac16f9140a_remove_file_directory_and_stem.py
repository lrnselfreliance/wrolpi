"""Remove file directory and stem.

Revision ID: 90ac16f9140a
Revises: 717f36a4da94
Create Date: 2022-12-16 09:58:32.238873

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '90ac16f9140a'
down_revision = '717f36a4da94'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP INDEX IF EXISTS file_directory_idx')
    session.execute('DROP INDEX IF EXISTS file_stem_idx')
    session.execute('ALTER TABLE file DROP COLUMN IF EXISTS directory')
    session.execute('ALTER TABLE file DROP COLUMN IF EXISTS stem')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE file ADD COLUMN directory TEXT')
    session.execute('ALTER TABLE file ADD COLUMN stem TEXT')
    session.execute('CREATE INDEX file_directory_idx ON file(directory)')
    session.execute('CREATE INDEX file_stem_idx ON file(stem)')
