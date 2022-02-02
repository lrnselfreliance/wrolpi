"""Files

Revision ID: 36cae041ad31
Revises: b97c1313f986
Create Date: 2022-02-01 11:05:57.605541

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '36cae041ad31'
down_revision = 'b97c1313f986'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''CREATE TABLE file (
        id BIGSERIAL PRIMARY KEY,
        path TEXT NOT NULL,
        title TEXT,
        mimetype TEXT,
        size INTEGER,
        modification_datetime TIMESTAMPTZ,
        textsearch tsvector GENERATED ALWAYS AS (
            setweight(to_tsvector('english'::regconfig, title), 'A'::"char")
            ) stored,
        idempotency TEXT
    )''')
    session.execute('CREATE INDEX file_path_idx ON file(path)')
    session.execute('CREATE INDEX file_mimetype_idx ON file(textsearch)')
    session.execute('CREATE INDEX file_textsearch_idx ON file(textsearch)')
    if not DOCKERIZED:
        session.execute('ALTER TABLE public.file OWNER TO wrolpi')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP INDEX IF EXISTS file_textsearch_idx')
    session.execute('DROP INDEX IF EXISTS file_mimetype_idx')
    session.execute('DROP INDEX IF EXISTS file_path_idx')

    session.execute('DROP TABLE IF EXISTS file')
