"""Drop channel.link.

Revision ID: d8fcdb7773c0
Revises: 2fb39c1861c7
Create Date: 2022-04-08 12:52:02.877449

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'd8fcdb7773c0'
down_revision = '2fb39c1861c7'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE channel DROP CONSTRAINT IF EXISTS channel_link_key')
    session.execute('ALTER TABLE channel DROP COLUMN IF EXISTS link')
    session.execute('DROP INDEX IF EXISTS channel_url_key')
    session.execute("UPDATE channel SET url=null WHERE url=''")
    session.execute('CREATE UNIQUE INDEX channel_url_key ON channel (url) WHERE url IS NOT NULL')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE channel ADD CONSTRAINT channel_link_key UNIQUE (link)')
    session.execute('ALTER TABLE channel ADD COLUMN IF NOT EXISTS link TEXT')
    # Notice we are not removing the channel_url_key constraint.
