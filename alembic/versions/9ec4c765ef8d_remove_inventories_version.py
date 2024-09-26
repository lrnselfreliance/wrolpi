"""Remove inventories version.

Revision ID: 9ec4c765ef8d
Revises: d4e446637f18
Create Date: 2024-09-24 16:01:41.716017

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '9ec4c765ef8d'
down_revision = 'd4e446637f18'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP TABLE IF EXISTS inventories_version')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''
    CREATE TABLE inventories_version (
        version SERIAL PRIMARY KEY NOT NULL
    )
    ''')

    if not DOCKERIZED:
        session.execute('ALTER TABLE public.inventories_version OWNER TO wrolpi')
