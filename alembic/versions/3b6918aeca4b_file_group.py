"""File group.

Revision ID: 3b6918aeca4b
Revises: 930b9b7adb79
Create Date: 2023-02-27 14:52:46.943351

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '3b6918aeca4b'
down_revision = '930b9b7adb79'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DELETE FROM video')  # noqa
    session.execute('ALTER TABLE video DROP COLUMN caption_path')
    session.execute('ALTER TABLE video DROP COLUMN censored')
    session.execute('ALTER TABLE video DROP COLUMN favorite')
    session.execute('ALTER TABLE video DROP COLUMN info_json_path')
    session.execute('ALTER TABLE video DROP COLUMN modification_datetime')
    session.execute('ALTER TABLE video DROP COLUMN poster_path')
    session.execute('ALTER TABLE video DROP COLUMN size')
    session.execute('ALTER TABLE video DROP COLUMN title')
    session.execute('ALTER TABLE video DROP COLUMN validated')
    session.execute('ALTER TABLE video DROP COLUMN video_path')

    session.execute('DELETE FROM archive')  # noqa
    session.execute('ALTER TABLE archive DROP COLUMN readability_json_path')
    session.execute('ALTER TABLE archive DROP COLUMN readability_path')
    session.execute('ALTER TABLE archive DROP COLUMN readability_txt_path')
    session.execute('ALTER TABLE archive DROP COLUMN screenshot_path')
    session.execute('ALTER TABLE archive DROP COLUMN singlefile_path')
    session.execute('ALTER TABLE archive DROP COLUMN title')
    session.execute('ALTER TABLE archive DROP COLUMN validated')

    session.execute('DELETE FROM ebook')  # noqa
    session.execute('ALTER TABLE ebook DROP COLUMN cover_path')
    session.execute('ALTER TABLE ebook DROP COLUMN ebook_path')
    session.execute('ALTER TABLE ebook DROP COLUMN title')

    session.execute('DROP TABLE IF EXISTS file')

    session.execute('''
    CREATE TABLE file_group (
        id BIGSERIAL PRIMARY KEY,
        data JSON,
        files JSON,
        full_stem TEXT NOT NULL UNIQUE,
        idempotency TIMESTAMP WITH TIME ZONE,
        indexed BOOLEAN DEFAULT FALSE,
        mimetype TEXT NOT NULL,
        model TEXT,
        modification_datetime TIMESTAMP WITH TIME ZONE,
        primary_path TEXT NOT NULL UNIQUE,
        size BIGINT,
        title TEXT,
        a_text TEXT,
        b_text TEXT,
        c_text TEXT,
        d_text TEXT,
        textsearch tsvector GENERATED ALWAYS AS (
            setweight(to_tsvector('english'::regconfig, COALESCE(a_text, '')), 'A'::"char") ||
            setweight(to_tsvector('english'::regconfig, COALESCE(b_text, '')), 'B'::"char") ||
            setweight(to_tsvector('english'::regconfig, COALESCE(c_text, '')), 'C'::"char") ||
            setweight(to_tsvector('english'::regconfig, COALESCE(d_text, '')), 'D'::"char")
        ) STORED
    )''')

    session.execute('ALTER TABLE video ADD COLUMN file_group_id BIGINT REFERENCES file_group(id) ON DELETE CASCADE NOT NULL UNIQUE')
    session.execute('ALTER TABLE ebook ADD COLUMN file_group_id BIGINT REFERENCES file_group(id) ON DELETE CASCADE NOT NULL UNIQUE')
    session.execute('ALTER TABLE archive ADD COLUMN file_group_id BIGINT REFERENCES file_group(id) ON DELETE CASCADE NOT NULL UNIQUE')

    session.execute('''
    CREATE TABLE tag (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        color VARCHAR(7)
    )''')

    session.execute('''
    CREATE TABLE tag_file (
        tag_id INTEGER REFERENCES tag(id),
        file_group_id BIGINT REFERENCES file_group(id) ON DELETE CASCADE,
        created_at TIMESTAMP WITH TIME ZONE,
        UNIQUE (tag_id, file_group_id)
    )''')

    session.execute('''
    INSERT INTO tag (name, color) VALUES 
        ('Automotive','#353535'),
        ('Child Care','#9858C5'),
        ('Clothing','#9858C5'),
        ('Comms','#ECD71C'),
        ('Cooking','#00A04A'),
        ('Electronics','#1b731f'),
        ('Entertainment','#000000'),
        ('Favorite','#000000'),
        ('Firearms','#000000'),
        ('Fire Safety','#000000'),
        ('First Aid','#C40405'),
        ('Food','#2F8055'),
        ('Food Preservation','#2F8055'),
        ('Fuel','#000000'),
        ('Garden','#3E8B22'),
        ('Husbandry','#000000'),
        ('Hygiene','#E6E6E6'),
        ('Knots','#000000'),
        ('Light','#EEEEEE'),
        ('Maps','#333333'),
        ('Mechanical','#7A7A7A'),
        ('Medical','#000000'),
        ('Nuclear','#000000'),
        ('Power','#D837FF'),
        ('Radio','#000000'),
        ('Schooling','#000000'),
        ('Security','#333333'),
        ('Shelter','#A18A62'),
        ('Social','#000000'),
        ('Survival','#A18A62'),
        ('Tools','#333333'),
        ('Water','#291BC2')
    ''')

    session.execute('UPDATE wrolpi_flag SET refresh_complete = false')

    if not DOCKERIZED:
        session.execute('ALTER TABLE public.file_group OWNER TO wrolpi')
        session.execute('ALTER TABLE public.tag OWNER TO wrolpi')
        session.execute('ALTER TABLE public.tag_file OWNER TO wrolpi')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP TABLE IF EXISTS tag_file')
    session.execute('DROP TABLE IF EXISTS tag')

    session.execute('ALTER TABLE video DROP COLUMN file_group_id')
    session.execute('ALTER TABLE ebook DROP COLUMN file_group_id')
    session.execute('ALTER TABLE archive DROP COLUMN file_group_id')

    session.execute('DROP TABLE file_group')

    session.execute('''
    create table file
    (
        path                  text not null primary key,
        idempotency           timestamp with time zone,
        indexed               boolean default false,
        mimetype              text,
        suffix                text,
        model                 text,
        associated            boolean default false,
        modification_datetime timestamp with time zone,
        size                  bigint,
        title                 text,
        a_text                text,
        b_text                text,
        c_text                text,
        d_text                text,
        textsearch            tsvector generated always as ((
                ((setweight(to_tsvector('english'::regconfig, COALESCE(a_text, ''::text)), 'A'::"char") ||
                  setweight(to_tsvector('english'::regconfig, COALESCE(b_text, ''::text)), 'B'::"char")) ||
                 setweight(to_tsvector('english'::regconfig, COALESCE(c_text, ''::text)), 'C'::"char")) ||
                setweight(to_tsvector('english'::regconfig, COALESCE(d_text, ''::text)), 'D'::"char"))) stored,
        full_stem             text
    );
    
    alter table file
        owner to postgres;
    
    create index file_mimetype_idx
        on file (mimetype);
    
    create index file_textsearch_idx
        on file using gin (textsearch);
    
    create index file_modification_datetime_idx
        on file (modification_datetime);
    
    create index file_size_idx
        on file (size);
    
    create index file_model_idx
        on file (model);
    
    create index file_idempotency_idx
        on file (idempotency);
    
    create index file_suffix_idx
        on file (suffix);
    
    create index file_full_stem_idx
        on file (full_stem);
    ''')

    session.execute('DELETE FROM video')  # noqa
    session.execute('ALTER TABLE video ADD COLUMN caption_path TEXT REFERENCES file(path)')
    session.execute('ALTER TABLE video ADD COLUMN censored BOOLEAN DEFAULT FALSE')
    session.execute('ALTER TABLE video ADD COLUMN favorite TIMESTAMPTZ')
    session.execute('ALTER TABLE video ADD COLUMN info_json_path TEXT REFERENCES file(path)')
    session.execute('ALTER TABLE video ADD COLUMN poster_path TEXT REFERENCES file(path)')
    session.execute('ALTER TABLE video ADD COLUMN video_path TEXT REFERENCES file(path)')
    session.execute('ALTER TABLE video ADD COLUMN modification_datetime TIMESTAMPTZ')
    session.execute('ALTER TABLE video ADD COLUMN size BIGINT')
    session.execute('ALTER TABLE video ADD COLUMN title TEXT')
    session.execute('ALTER TABLE video ADD COLUMN validated BOOLEAN DEFAULT FALSE')

    session.execute('DELETE FROM archive')  # noqa
    session.execute('ALTER TABLE archive ADD COLUMN readability_json_path TEXT REFERENCES file(path)')
    session.execute('ALTER TABLE archive ADD COLUMN readability_path TEXT REFERENCES file(path)')
    session.execute('ALTER TABLE archive ADD COLUMN readability_txt_path TEXT REFERENCES file(path)')
    session.execute('ALTER TABLE archive ADD COLUMN screenshot_path TEXT REFERENCES file(path)')
    session.execute('ALTER TABLE archive ADD COLUMN singlefile_path TEXT REFERENCES file(path)')
    session.execute('ALTER TABLE archive ADD COLUMN title TEXT')
    session.execute('ALTER TABLE archive ADD COLUMN validated BOOLEAN DEFAULT FALSE')

    session.execute('DELETE FROM ebook')  # noqa
    session.execute('ALTER TABLE ebook ADD COLUMN cover_path TEXT REFERENCES file(path)')
    session.execute('ALTER TABLE ebook ADD COLUMN ebook_path TEXT REFERENCES file(path)')
    session.execute('ALTER TABLE ebook ADD COLUMN title TEXT')

    session.execute('UPDATE wrolpi_flag SET refresh_complete = false')

    if not DOCKERIZED:
        session.execute('ALTER TABLE public.file OWNER TO wrolpi')
