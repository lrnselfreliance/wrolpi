"""Create MapFile table.

Revision ID: 2fb39c1861c7
Revises: 36cae041ad31
Create Date: 2022-03-03 19:13:39.997580

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '2fb39c1861c7'
down_revision = '36cae041ad31'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''CREATE TABLE map_file (
        id SERIAL PRIMARY KEY,
        path TEXT NOT NULL,
        imported BOOLEAN DEFAULT FALSE,
        size BIGINT
    )''')

    if not DOCKERIZED:
        session.execute('ALTER TABLE public.map_file OWNER TO wrolpi')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('DROP TABLE IF EXISTS map_file')
