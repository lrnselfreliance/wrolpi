"""Covering indexes for the Collection listing.

Listing Collections read every channel row (for video_count/total_size) and every download
row of those Collections (for the minimum frequency).  Both tables store yt-dlp info_json,
so their rows are tens of KB and each sits on its own scattered page; from a cold disk cache
that was 10+ seconds.  These indexes answer both queries without touching a row.

Revision ID: 2026_09_28_1200
Revises: 2026_09_27_1200
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '2026_09_28_1200'
down_revision = '2026_09_27_1200'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE INDEX IF NOT EXISTS channel_collection_summary_idx'
               ' ON channel (collection_id, video_count, total_size)')
    op.execute('CREATE INDEX IF NOT EXISTS download_collection_frequency_idx'
               ' ON download (collection_id, frequency)')


def downgrade():
    op.execute('DROP INDEX IF EXISTS channel_collection_summary_idx')
    op.execute('DROP INDEX IF EXISTS download_collection_frequency_idx')
