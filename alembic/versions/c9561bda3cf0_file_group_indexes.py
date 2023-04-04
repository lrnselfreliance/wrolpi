"""file_group indexes

Revision ID: c9561bda3cf0
Revises: 3b6918aeca4b
Create Date: 2023-03-25 20:45:00.470336

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'c9561bda3cf0'
down_revision = '3b6918aeca4b'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('CREATE INDEX file_group_full_stem_idx ON file_group(full_stem)')
    session.execute('CREATE INDEX file_group_mimetype_idx ON file_group(mimetype)')
    session.execute('CREATE INDEX file_group_model_idx ON file_group(model)')
    session.execute('CREATE INDEX file_group_modification_datetime_idx ON file_group(modification_datetime)')
    session.execute('CREATE INDEX file_group_size_ix ON file_group(size)')
    session.execute('CREATE INDEX file_group_textsearch_idx ON file_group USING GIN(textsearch)')

    session.execute('CREATE INDEX archive_domain_id_idx ON archive(domain_id)')

    session.execute('CREATE INDEX domains_domain_idx ON domains(domain)')

    session.execute('CREATE INDEX video_source_id_idx ON video(source_id)')
    session.execute('CREATE INDEX video_upload_date_idx ON video(upload_date)')
    session.execute('CREATE INDEX video_view_count_idx ON video(view_count)')
    session.execute('CREATE INDEX video_viewed_idx ON video(viewed)')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP INDEX IF EXISTS file_group_full_stem_idx')
    session.execute('DROP INDEX IF EXISTS file_group_mimetype_idx')
    session.execute('DROP INDEX IF EXISTS file_group_model_idx')
    session.execute('DROP INDEX IF EXISTS file_group_modification_datetime_idx')
    session.execute('DROP INDEX IF EXISTS file_group_size_ix')

    session.execute('DROP INDEX IF EXISTS archive_domain_id_idx')

    session.execute('DROP INDEX IF EXISTS domains_domain_idx')

    session.execute('DROP INDEX IF EXISTS video_source_id_idx')
    session.execute('DROP INDEX IF EXISTS video_upload_date_idx')
    session.execute('DROP INDEX IF EXISTS video_view_count_idx')
    session.execute('DROP INDEX IF EXISTS video_viewed_idx')
