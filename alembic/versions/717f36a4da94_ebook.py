"""Ebook

Revision ID: 717f36a4da94
Revises: d0bbe45e56c3
Create Date: 2022-12-09 15:32:32.228539

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '717f36a4da94'
down_revision = 'd0bbe45e56c3'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''
    DROP INDEX IF EXISTS ebook_title_idx;
    DROP INDEX IF EXISTS ebook_size_idx;
    DROP INDEX IF EXISTS ebook_creator_idx;
    DROP INDEX IF EXISTS ebook_ebook_path_idx;
    DROP INDEX IF EXISTS ebook_cover_path_idx;
    DROP TABLE IF EXISTS ebook;
    ''')

    session.execute('''
    CREATE TABLE ebook (
        id SERIAL PRIMARY KEY,
        size INTEGER,
        title TEXT,
        creator TEXT,
        ebook_path TEXT REFERENCES file(path) ON DELETE CASCADE,
        cover_path TEXT REFERENCES file(path) ON DELETE CASCADE
    )''')

    if not DOCKERIZED:
        session.execute('ALTER TABLE public.ebook OWNER TO wrolpi')

    session.execute('CREATE INDEX ebook_title_idx ON ebook(title)')
    session.execute('CREATE INDEX ebook_size_idx ON ebook(size)')
    session.execute('CREATE INDEX ebook_creator_idx ON ebook(creator)')
    session.execute('CREATE INDEX ebook_ebook_path_idx ON ebook(ebook_path)')
    session.execute('CREATE INDEX ebook_cover_path_idx ON ebook(cover_path)')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''
    DROP INDEX IF EXISTS ebook_title_idx;
    DROP INDEX IF EXISTS ebook_size_idx;
    DROP INDEX IF EXISTS ebook_creator_idx;
    DROP INDEX IF EXISTS ebook_ebook_path_idx;
    DROP INDEX IF EXISTS ebook_cover_path_idx;
    DROP TABLE IF EXISTS ebook;
    ''')
