"""Drop inventory tables (inventory is now config-only).

The inventory system no longer uses the database; each inventory is a YAML file at config/inventory/<slug>.yaml.
Legacy data is migrated to those files on startup (see modules/inventory/migrate.py) before these tables are dropped.

Revision ID: b2e4f6a8c1d3
Revises: a7b1c2d3e4f5
Create Date: 2026-06-13 00:00:00.000000

"""
import os

from alembic import op
from sqlalchemy.orm import Session

revision = 'b2e4f6a8c1d3'
down_revision = 'a7b1c2d3e4f5'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    # `item` first due to its foreign key to `inventory`.
    session.execute('DROP TABLE IF EXISTS public.item')
    session.execute('DROP TABLE IF EXISTS public.inventory')
    session.execute('DROP TABLE IF EXISTS public.inventories_version')


def downgrade():
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
