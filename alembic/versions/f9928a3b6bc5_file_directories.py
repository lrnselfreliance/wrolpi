"""File Directories

Revision ID: f9928a3b6bc5
Revises: c9561bda3cf0
Create Date: 2023-04-18 16:58:40.043115

"""
import os
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'f9928a3b6bc5'
down_revision = 'c9561bda3cf0'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''
        CREATE TABLE directory (
            path TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            idempotency TIMESTAMP WITH TIME ZONE DEFAULT current_timestamp
        )
    ''')

    session.execute('CREATE INDEX directory_name_idx ON directory(name)')

    if not DOCKERIZED:
        session.execute('ALTER TABLE public.directory OWNER TO wrolpi')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP INDEX IF EXISTS directory_name_idx')
    session.execute('DROP TABLE IF EXISTS directory')
