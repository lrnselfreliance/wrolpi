"""Inventories Version

Revision ID: 25c19ea2d295
Revises: 7cb1a9eb38b5
Create Date: 2021-08-03 20:58:24.939447

"""
from alembic import op

# revision identifiers, used by Alembic.
from sqlalchemy.orm import Session

revision = '25c19ea2d295'
down_revision = '7cb1a9eb38b5'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''
    CREATE TABLE inventories_version (
        version SERIAL PRIMARY KEY NOT NULL
    )
    ''')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''
    DROP TABLE inventories_version
    ''')
