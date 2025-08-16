"""Lower FileGroup.primary_path

Revision ID: 158973fda20f
Revises: 69e9754d1a63
Create Date: 2025-08-16 10:54:58.874094

"""
import os
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '158973fda20f'
down_revision = '69e9754d1a63'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    op.execute('CREATE INDEX file_group_primary_path_lower_idx ON file_group (LOWER(primary_path))')


def downgrade():
    op.execute('DROP INDEX IF EXISTS file_group_primary_path_lower_idx')
