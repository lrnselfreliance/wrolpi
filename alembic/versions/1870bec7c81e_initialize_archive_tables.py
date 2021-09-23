"""Initialize archive tables.

Revision ID: 1870bec7c81e
Revises: 053f17f07c4e
Create Date: 2021-09-22 18:31:15.056697

"""
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '1870bec7c81e'
down_revision = '053f17f07c4e'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''
    CREATE TABLE domains (
        id SERIAL PRIMARY KEY,
        domain TEXT NOT NULL UNIQUE,
        directory TEXT NOT NULL UNIQUE
    )''')

    session.execute('''
    CREATE TABLE url (
        id SERIAL PRIMARY KEY,
        domain_id INTEGER REFERENCES domains(id) NOT NULL,
        url TEXT NOT NULL UNIQUE,
        latest_datetime TIMESTAMPTZ
    )''')

    session.execute('''
    CREATE TABLE archive (
        id SERIAL PRIMARY KEY,
        url_id INTEGER REFERENCES url(id) ON DELETE CASCADE NOT NULL,
        domain_id INTEGER REFERENCES domains(id) ON DELETE CASCADE NOT NULL,
        singlefile_path TEXT NOT NULL,
        readability_path TEXT,
        readability_txt_path TEXT,
        screenshot_path TEXT,
        title TEXT,
        archive_datetime TIMESTAMPTZ
    )''')

    session.execute('ALTER TABLE url ADD COLUMN latest_id INTEGER REFERENCES archive(id)')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP TABLE IF EXISTS domains CASCADE')
    session.execute('DROP TABLE IF EXISTS url CASCADE')
    session.execute('DROP TABLE IF EXISTS archive CASCADE')
