"""Doc indexer.

Revision ID: 1c041aeee0fc
Revises: d96a04eb2785
Create Date: 2024-03-05 16:54:34.478974

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '1c041aeee0fc'
down_revision = 'd96a04eb2785'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    # Re-index Word documents.
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute(
        """
        UPDATE file_group
        SET indexed=false
        WHERE mimetype in
            ('application/msword','application/vnd.openxmlformats-officedocument.wordprocessingml.document')
   """)


def downgrade():
    pass
