"""file_group.effective_date trigger

Revision ID: 4f03b9548f6e
Revises: 54c19aa847da
Create Date: 2025-08-17 10:49:35.754548

"""
import os
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '4f03b9548f6e'
down_revision = '54c19aa847da'
branch_labels = None
depends_on = None


def upgrade():
    # Create trigger function
    op.execute("""
               CREATE OR REPLACE FUNCTION update_effective_datetime()
                   RETURNS TRIGGER AS
               $$
               BEGIN
                   NEW.effective_datetime = COALESCE(NEW.published_datetime, NEW.download_datetime);
                   RETURN NEW;
               END;
               $$ LANGUAGE plpgsql;
               """)

    # Create trigger
    op.execute("""
               CREATE TRIGGER file_group_effective_datetime_trigger
                   BEFORE INSERT OR UPDATE OF published_datetime, download_datetime
                   ON file_group
                   FOR EACH ROW
               EXECUTE FUNCTION update_effective_datetime();
               """)


def downgrade():
    # Drop trigger
    op.execute("DROP TRIGGER IF EXISTS file_group_effective_datetime_trigger ON file_group")

    # Drop trigger function
    op.execute("DROP FUNCTION IF EXISTS update_effective_datetime")
