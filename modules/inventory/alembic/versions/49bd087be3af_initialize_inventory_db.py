"""Initialize Inventory DB.

Revision ID: 49bd087be3af
Revises:
Create Date: 2021-09-15 15:47:42.689990

"""
from alembic import op

from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '49bd087be3af'
down_revision = None
branch_labels = None
depends_on = None


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


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP TABLE IF EXISTS public.inventories_version''')
    session.execute('DROP TABLE IF EXISTS public.item''')
    session.execute('DROP TABLE IF EXISTS public.inventory''')
