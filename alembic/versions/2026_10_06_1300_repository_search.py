"""Search git Repos by name and README: repository.search_name/readme_text and repository_fts.

Revision ID: 2026_10_06_1300
Revises: 2026_10_06_1200
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '2026_10_06_1300'
down_revision = '2026_10_06_1200'
branch_labels = None
depends_on = None


def upgrade():
    from wrolpi.schema_ddl import install_raw_ddl

    op.add_column('repository', sa.Column('search_name', sa.String(), nullable=True))
    op.add_column('repository', sa.Column('readme_text', sa.Text(), nullable=True))
    op.execute('''
        UPDATE repository SET search_name = TRIM(
            COALESCE((SELECT name FROM collection WHERE collection.id = repository.collection_id), '')
            || ' ' || COALESCE(owner, ''))
    ''')

    # Creates repository_fts and its triggers now that the columns exist.  The README text is filled by the next
    # update of each Repo.
    install_raw_ddl(op.get_bind())
    op.execute("INSERT INTO repository_fts(repository_fts) VALUES('rebuild')")


def downgrade():
    for name in ('repository_fts_ai', 'repository_fts_ad', 'repository_fts_au'):
        op.execute(f'DROP TRIGGER IF EXISTS {name}')
    op.execute('DROP TABLE IF EXISTS repository_fts')
    with op.batch_alter_table('repository') as batch_op:
        batch_op.drop_column('readme_text')
        batch_op.drop_column('search_name')
