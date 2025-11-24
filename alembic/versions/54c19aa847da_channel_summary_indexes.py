"""Channel summary columns, triggers and indexes.

Revision ID: 54c19aa847da
Revises: 158973fda20f
Create Date: 2025-08-16 11:45:48.190427

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '54c19aa847da'
down_revision = '158973fda20f'
branch_labels = None
depends_on = None


def upgrade():
    # Add columns
    op.execute("""
               ALTER TABLE channel
                   ADD COLUMN video_count   INTEGER DEFAULT 0 NOT NULL,
                   ADD COLUMN total_size    BIGINT  DEFAULT 0 NOT NULL,
                   ADD COLUMN minimum_frequency INTEGER;
               """)

    # Populate columns
    op.execute("""
               UPDATE channel
               SET video_count   = (SELECT COUNT(*)
                                    FROM video
                                    WHERE channel_id = channel.id),
                   total_size    = (SELECT COALESCE(SUM(fg.size), 0)::BIGINT
                                    FROM video v
                                             LEFT JOIN file_group fg ON v.file_group_id = fg.id
                                    WHERE v.channel_id = channel.id),
                   minimum_frequency = (SELECT MIN(frequency)
                                    FROM download
                                    WHERE channel_id = channel.id);
               """)

    # Create trigger functions
    op.execute("""
               CREATE OR REPLACE FUNCTION update_channel_video_count()
                   RETURNS TRIGGER AS
               $$
               BEGIN
                   UPDATE channel
                   SET video_count = (SELECT COUNT(*) FROM video WHERE channel_id = NEW.channel_id)
                   WHERE id = NEW.channel_id;
                   RETURN NEW;
               END;
               $$ LANGUAGE plpgsql;
               """)
    op.execute("""
               CREATE OR REPLACE FUNCTION update_channel_size()
                   RETURNS TRIGGER AS
               $$
               BEGIN
                   UPDATE channel
                   SET total_size = (SELECT COALESCE(SUM(fg.size), 0)::BIGINT
                                     FROM video v
                                              LEFT JOIN file_group fg ON v.file_group_id = fg.id
                                     WHERE v.channel_id = NEW.id)
                   WHERE id = NEW.id;
                   RETURN NEW;
               END;
               $$ LANGUAGE plpgsql;
               """)
    op.execute("""
               CREATE OR REPLACE FUNCTION update_channel_minimum_frequency()
                   RETURNS TRIGGER AS
               $$
               BEGIN
                   UPDATE channel
                   SET minimum_frequency = (SELECT MIN(frequency) FROM download WHERE channel_id = NEW.channel_id)
                   WHERE id = NEW.channel_id;
                   RETURN NEW;
               END;
               $$ LANGUAGE plpgsql;
               """)

    # Create triggers
    op.execute("""
               CREATE TRIGGER video_count_trigger
                   AFTER INSERT OR DELETE
                   ON video
                   FOR EACH ROW
               EXECUTE FUNCTION update_channel_video_count();
               """)
    op.execute("""
               CREATE TRIGGER video_size_trigger
                   AFTER INSERT OR DELETE
                   ON video
                   FOR EACH ROW
               EXECUTE FUNCTION update_channel_size();
               """)
    op.execute("""
               CREATE TRIGGER file_group_size_trigger
                   AFTER UPDATE OF size
                   ON file_group
                   FOR EACH ROW
                   WHEN (OLD.size IS DISTINCT FROM NEW.size)
               EXECUTE FUNCTION update_channel_size();
               """)
    op.execute("""
               CREATE TRIGGER download_frequency_trigger
                   AFTER INSERT OR UPDATE OF frequency OR DELETE
                   ON download
                   FOR EACH ROW
               EXECUTE FUNCTION update_channel_minimum_frequency();
               """)

    # Create indexes
    op.execute("""
               CREATE INDEX channel_video_count_idx ON channel (video_count);
               CREATE INDEX channel_total_size_idx ON channel (total_size);
               CREATE INDEX channel_minimum_frequency_idx ON channel (minimum_frequency);
               """)


def downgrade():
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS video_count_trigger ON video;")
    op.execute("DROP TRIGGER IF EXISTS video_size_trigger ON video;")
    op.execute("DROP TRIGGER IF EXISTS file_group_size_trigger ON file_group;")
    op.execute("DROP TRIGGER IF EXISTS download_frequency_trigger ON download;")

    # Drop trigger functions
    op.execute("DROP FUNCTION IF EXISTS update_channel_video_count;")
    op.execute("DROP FUNCTION IF EXISTS update_channel_size;")
    op.execute("DROP FUNCTION IF EXISTS update_channel_minimum_frequency;")

    # Drop indexes
    op.execute("DROP INDEX IF EXISTS channel_minimum_frequency_idx;")
    op.execute("DROP INDEX IF EXISTS channel_total_size_idx;")
    op.execute("DROP INDEX IF EXISTS channel_video_count_idx;")

    # Drop columns
    op.execute("""
               ALTER TABLE channel
                   DROP COLUMN IF EXISTS minimum_frequency,
                   DROP COLUMN IF EXISTS total_size,
                   DROP COLUMN IF EXISTS video_count;
               """)
