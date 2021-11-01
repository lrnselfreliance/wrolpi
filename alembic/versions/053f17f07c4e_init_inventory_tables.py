"""Init inventory tables.

Revision ID: 053f17f07c4e
Revises: f0d0086a73d1
Create Date: 2021-09-20 16:21:00.322598

"""
import os

from alembic import op
from sqlalchemy.orm import Session

revision = '053f17f07c4e'
down_revision = 'f0d0086a73d1'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''
    CREATE TABLE inventories_version (
        version SERIAL PRIMARY KEY NOT NULL
    )
    ''')

    session.execute('''
    CREATE TABLE public.inventory (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        viewed_at TIMESTAMP WITHOUT TIME ZONE,
        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMP WITHOUT TIME ZONE
    )''')

    session.execute('''
    CREATE TABLE public.item (
        id SERIAL PRIMARY KEY,
        inventory_id INTEGER REFERENCES inventory(id) ON DELETE CASCADE,
        brand TEXT,
        name TEXT,
        count DECIMAL,
        item_size DECIMAL,
        unit TEXT,
        serving INTEGER,
        category TEXT,
        subcategory TEXT,
        expiration_date DATE,
        purchase_date DATE,
        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMP WITHOUT TIME ZONE
    )''')

    if not DOCKERIZED:
        session.execute('ALTER TABLE public.inventories_version OWNER TO wrolpi')
        session.execute('ALTER TABLE public.inventory OWNER TO wrolpi')
        session.execute('ALTER TABLE public.item OWNER TO wrolpi')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP TABLE IF EXISTS public.inventories_version''')
    session.execute('DROP TABLE IF EXISTS public.item''')
    session.execute('DROP TABLE IF EXISTS public.inventory''')
