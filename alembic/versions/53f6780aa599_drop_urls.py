"""Drop URLs.

Revision ID: 53f6780aa599
Revises: 31896cc29b71
Create Date: 2022-01-03 12:25:51.575505

"""
import os

from alembic import op
from sqlalchemy import text
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '53f6780aa599'
down_revision = '31896cc29b71'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    urls = {i['id']: i['url'] for i in session.execute(text('SELECT id, url FROM url'))}
    archives = {i['id']: i['url_id'] for i in session.execute(text('SELECT id, url_id FROM archive'))}

    session.execute(text('ALTER TABLE archive ADD COLUMN url TEXT'))

    for archive_id, url_id in archives.items():
        session.execute(
            text('UPDATE archive SET url = :url WHERE id = :id'),
            {'url': urls[url_id], 'id': archive_id}
        )

    session.execute(text('ALTER TABLE archive DROP COLUMN url_id'))
    session.execute(text('DROP TABLE url'))
