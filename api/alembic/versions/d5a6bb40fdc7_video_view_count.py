"""video.view_count

Revision ID: d5a6bb40fdc7
Revises: 25c19ea2d295
Create Date: 2021-08-11 11:14:48.620055

"""
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'd5a6bb40fdc7'
down_revision = '25c19ea2d295'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''
    ALTER TABLE video ADD COLUMN view_count INTEGER;
    ''')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''
    ALTER TABLE video DROP COLUMN IF EXISTS view_count;
    ''')
