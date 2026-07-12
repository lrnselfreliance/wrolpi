"""Raw SQLite DDL shared by the Alembic baseline and the test database.

SQLAlchemy models (`Base.metadata`) define the tables; this module holds everything the models
cannot express: triggers and the FTS5 full-text-search tables (see `wrolpi.fts`).

`install_raw_ddl` is executed by BOTH:
  * the Alembic baseline migration (production databases), and
  * `wrolpi.conftest.test_db` (test databases, after `Base.metadata.create_all`),
so tests exercise exactly the schema production runs.

All statements are idempotent (IF NOT EXISTS).
"""

# Triggers maintaining the summary columns `channel.video_count`, `channel.total_size`,
# `channel.minimum_frequency` and `file_group.effective_datetime`.
#
# These are re-authored from the old PL/pgSQL triggers (see git history of alembic/versions/).
# The old triggers had known bugs which are fixed here:
#   * video_count used NEW.channel_id on DELETE (always NULL in Postgres), so counts never
#     decremented, and did not fire on UPDATE OF channel_id (re-parenting).
#   * total_size used NEW.id (a video/file_group id) as the channel id.
TRIGGER_DDL = [
    # channel.video_count + channel.total_size follow the videos in the channel.
    '''
    CREATE TRIGGER IF NOT EXISTS video_insert_channel_summary
    AFTER INSERT ON video WHEN new.channel_id IS NOT NULL
    BEGIN
        UPDATE channel SET
            video_count = (SELECT COUNT(*) FROM video WHERE channel_id = channel.id),
            total_size = (SELECT COALESCE(SUM(fg.size), 0) FROM video v
                          LEFT JOIN file_group fg ON v.file_group_id = fg.id
                          WHERE v.channel_id = channel.id)
        WHERE id = new.channel_id;
    END
    ''',
    '''
    CREATE TRIGGER IF NOT EXISTS video_delete_channel_summary
    AFTER DELETE ON video WHEN old.channel_id IS NOT NULL
    BEGIN
        UPDATE channel SET
            video_count = (SELECT COUNT(*) FROM video WHERE channel_id = channel.id),
            total_size = (SELECT COALESCE(SUM(fg.size), 0) FROM video v
                          LEFT JOIN file_group fg ON v.file_group_id = fg.id
                          WHERE v.channel_id = channel.id)
        WHERE id = old.channel_id;
    END
    ''',
    # Re-parenting a video (or changing its FileGroup) updates both affected channels.
    '''
    CREATE TRIGGER IF NOT EXISTS video_update_channel_summary
    AFTER UPDATE OF channel_id, file_group_id ON video
    BEGIN
        UPDATE channel SET
            video_count = (SELECT COUNT(*) FROM video WHERE channel_id = channel.id),
            total_size = (SELECT COALESCE(SUM(fg.size), 0) FROM video v
                          LEFT JOIN file_group fg ON v.file_group_id = fg.id
                          WHERE v.channel_id = channel.id)
        WHERE id IN (old.channel_id, new.channel_id);
    END
    ''',
    # A FileGroup's size changed; update the Channel of the Video which owns it (if any).
    '''
    CREATE TRIGGER IF NOT EXISTS file_group_size_channel_summary
    AFTER UPDATE OF size ON file_group WHEN old.size IS NOT new.size
    BEGIN
        UPDATE channel SET
            total_size = (SELECT COALESCE(SUM(fg.size), 0) FROM video v
                          LEFT JOIN file_group fg ON v.file_group_id = fg.id
                          WHERE v.channel_id = channel.id)
        WHERE id = (SELECT channel_id FROM video WHERE file_group_id = new.id);
    END
    ''',
    # channel.minimum_frequency follows the Downloads of the Channel's Collection.
    '''
    CREATE TRIGGER IF NOT EXISTS download_insert_minimum_frequency
    AFTER INSERT ON download WHEN new.collection_id IS NOT NULL
    BEGIN
        UPDATE channel SET
            minimum_frequency = (SELECT MIN(frequency) FROM download
                                 WHERE collection_id = channel.collection_id)
        WHERE collection_id = new.collection_id;
    END
    ''',
    '''
    CREATE TRIGGER IF NOT EXISTS download_update_minimum_frequency
    AFTER UPDATE OF frequency, collection_id ON download
    BEGIN
        UPDATE channel SET
            minimum_frequency = (SELECT MIN(frequency) FROM download
                                 WHERE collection_id = channel.collection_id)
        WHERE collection_id IN (old.collection_id, new.collection_id);
    END
    ''',
    '''
    CREATE TRIGGER IF NOT EXISTS download_delete_minimum_frequency
    AFTER DELETE ON download WHEN old.collection_id IS NOT NULL
    BEGIN
        UPDATE channel SET
            minimum_frequency = (SELECT MIN(frequency) FROM download
                                 WHERE collection_id = channel.collection_id)
        WHERE collection_id = old.collection_id;
    END
    ''',
    # file_group.effective_datetime = COALESCE(published_datetime, download_datetime).
    # Also maintained by an ORM event (wrolpi.files.models.update_effective_datetime); these
    # triggers cover raw-SQL writers.  The WHEN clause avoids rewriting rows the ORM already set.
    '''
    CREATE TRIGGER IF NOT EXISTS file_group_effective_datetime_insert
    AFTER INSERT ON file_group
    WHEN new.effective_datetime IS NOT COALESCE(new.published_datetime, new.download_datetime)
    BEGIN
        UPDATE file_group
        SET effective_datetime = COALESCE(new.published_datetime, new.download_datetime)
        WHERE id = new.id;
    END
    ''',
    '''
    CREATE TRIGGER IF NOT EXISTS file_group_effective_datetime_update
    AFTER UPDATE OF published_datetime, download_datetime ON file_group
    WHEN new.effective_datetime IS NOT COALESCE(new.published_datetime, new.download_datetime)
    BEGIN
        UPDATE file_group
        SET effective_datetime = COALESCE(new.published_datetime, new.download_datetime)
        WHERE id = new.id;
    END
    ''',
]


def install_raw_ddl(conn):
    """Install all raw DDL (triggers + FTS5) on a SQLite database.

    `conn` may be a SQLAlchemy Connection (e.g. `op.get_bind()` in Alembic) or a raw
    `sqlite3.Connection`.  Idempotent."""
    from wrolpi import fts

    for statement in [*TRIGGER_DDL, *fts.FTS_DDL]:
        conn.execute(statement)
