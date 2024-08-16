"""Tag names migration

Revision ID: 2bfb3b50b178
Revises: 8d0d81bc9c34
Create Date: 2024-07-31 14:58:29.583029

"""
import os
import sys

from alembic import op
from sqlalchemy.orm import Session

from wrolpi.common import escape_file_name
from wrolpi.tags import Tag, get_tags_config

# revision identifiers, used by Alembic.
revision = '2bfb3b50b178'
down_revision = '8d0d81bc9c34'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    need_commit = False
    tags = session.query(Tag).all()
    for tag in tags:
        escaped_name = escape_file_name(tag.name)
        if escaped_name != tag.name:
            tag.name = escaped_name
            session.flush([tag, ])
            need_commit = True

    if need_commit:
        session.commit()

    try:
        config = get_tags_config()
        config.initialize()
        config.save_tags(session, ignore_lock=True)
    except FileNotFoundError:
        print(f'Failed to save tags config probably because media directory does not exist', file=sys.stderr)


def downgrade():
    pass
