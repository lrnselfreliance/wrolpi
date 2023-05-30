"""Zim

Revision ID: 751aecf46b88
Revises: 75d34a2b442d
Create Date: 2023-06-04 19:48:41.305111

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '751aecf46b88'
down_revision = '75d34a2b442d'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''
    CREATE TABLE zim (
        id SERIAL PRIMARY KEY,
        path TEXT NOT NULL UNIQUE,
        file_group_id BIGINT REFERENCES file_group(id) ON DELETE CASCADE NOT NULL
    )''')

    session.execute('''
    CREATE TABLE tag_zim (
        tag_id INTEGER REFERENCES tag(id),
        zim_id INTEGER REFERENCES zim(id) ON DELETE CASCADE,
        zim_entry TEXT NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (tag_id, zim_id, zim_entry)
    )''')

    session.execute('''
    CREATE TABLE zim_subscription (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        language TEXT NOT NULL,
        download_id INTEGER NOT NULL REFERENCES download(id) ON DELETE CASCADE
    )
    ''')

    # We want to index all Zim files using `zim_modeler`
    session.execute("UPDATE file_group SET indexed=false WHERE primary_path ILIKE '%.zim'")

    if not DOCKERIZED:
        session.execute('ALTER TABLE public.zim OWNER TO wrolpi')
        session.execute('ALTER TABLE public.tag_zim OWNER TO wrolpi')
        session.execute('ALTER TABLE public.zim_subscription OWNER TO wrolpi')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP TABLE IF EXISTS zim_subscription')
    session.execute('DROP TABLE IF EXISTS tag_zim')
    session.execute('DROP TABLE IF EXISTS zim')
    session.execute("UPDATE file_group SET indexed=false WHERE primary_path ILIKE '%.zim'")
