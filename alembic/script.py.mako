"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
import os
from alembic import op
from sqlalchemy.orm import Session
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    ${upgrades if upgrades else "pass"}

    if not DOCKERIZED:
        session.execute('ALTER TABLE public.TABLE_NAME OWNER TO wrolpi')


def downgrade():
    ${downgrades if downgrades else "pass"}
