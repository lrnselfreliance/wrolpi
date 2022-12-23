"""WROLPi flags

Revision ID: 930b9b7adb79
Revises: 90ac16f9140a
Create Date: 2022-12-20 21:02:28.975897

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '930b9b7adb79'
down_revision = '90ac16f9140a'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''CREATE TABLE wrolpi_flag(
        id SERIAL PRIMARY KEY,
        refresh_complete BOOLEAN DEFAULT FALSE
    )''')

    if not DOCKERIZED:
        session.execute('ALTER TABLE public.wrolpi_flag OWNER TO wrolpi')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP TABLE IF EXISTS wrolpi_flag')
