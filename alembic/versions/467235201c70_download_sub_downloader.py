"""Download.sub_downloader.

Revision ID: 467235201c70
Revises: 1a70196c05bb
Create Date: 2022-05-20 11:51:58.064020

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '467235201c70'
down_revision = '1a70196c05bb'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    session = Session(bind=op.get_bind())
    session.execute('ALTER TABLE download ADD COLUMN IF NOT EXISTS sub_downloader TEXT')


def downgrade():
    session = Session(bind=op.get_bind())
    session.execute('ALTER TABLE download DROP COLUMN IF EXISTS sub_downloader')
