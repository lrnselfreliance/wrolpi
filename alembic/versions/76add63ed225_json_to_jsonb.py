"""json_to_jsonb

Revision ID: 76add63ed225
Revises: 26c5a62ec683
Create Date: 2026-01-06 06:13:14.044016

"""
import os
from alembic import op
from sqlalchemy.orm import Session
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '76add63ed225'
down_revision = '26c5a62ec683'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    # Convert FileGroup columns from JSON to JSONB
    session.execute(text('ALTER TABLE file_group ALTER COLUMN data TYPE jsonb USING data::jsonb'))
    session.execute(text('ALTER TABLE file_group ALTER COLUMN files TYPE jsonb USING files::jsonb'))

    # Convert Video column from JSON to JSONB
    session.execute(text('ALTER TABLE video ALTER COLUMN ffprobe_json TYPE jsonb USING ffprobe_json::jsonb'))

    # Convert Channel column from JSON to JSONB
    session.execute(text('ALTER TABLE channel ALTER COLUMN info_json TYPE jsonb USING info_json::jsonb'))


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    # Revert FileGroup columns from JSONB to JSON
    session.execute(text('ALTER TABLE file_group ALTER COLUMN data TYPE json USING data::json'))
    session.execute(text('ALTER TABLE file_group ALTER COLUMN files TYPE json USING files::json'))

    # Revert Video column from JSONB to JSON
    session.execute(text('ALTER TABLE video ALTER COLUMN ffprobe_json TYPE json USING ffprobe_json::json'))

    # Revert Channel column from JSONB to JSON
    session.execute(text('ALTER TABLE channel ALTER COLUMN info_json TYPE json USING info_json::json'))
