"""Download settings

Revision ID: c72d305cf11e
Revises: d2eace02f5b9
Create Date: 2022-10-14 13:00:30.333384

"""
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'c72d305cf11e'
down_revision = 'd2eace02f5b9'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE download ADD COLUMN settings JSONB')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE download DROP COLUMN IF EXISTS settings')
