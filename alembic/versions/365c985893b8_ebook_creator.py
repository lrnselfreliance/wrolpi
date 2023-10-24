"""eBook creator.

Revision ID: 365c985893b8
Revises: 5ad9efbf3570
Create Date: 2023-10-29 16:54:28.319427

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '365c985893b8'
down_revision = '5ad9efbf3570'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''
        UPDATE file_group
        SET author=creator
        FROM ebook
        WHERE ebook.file_group_id = file_group.id
    ''')
    session.execute('DROP INDEX IF EXISTS ebook_creator_idx')
    session.execute('ALTER TABLE ebook DROP COLUMN IF EXISTS creator')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE ebook ADD COLUMN IF NOT EXISTS creator TEXT')
    session.execute('''
        UPDATE ebook
        SET creator=author
        FROM file_group
        WHERE
            ebook.file_group_id = file_group.id
            AND model = 'ebook'
    ''')
    session.execute('CREATE INDEX IF NOT EXISTS ebook_creator_idx ON ebook(creator)')
