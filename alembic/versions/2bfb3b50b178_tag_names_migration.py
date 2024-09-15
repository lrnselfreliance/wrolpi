"""MTag names migration

Revision ID: 2bfb3b50b178
Revises: 8d0d81bc9c34
Create Date: 2024-07-31 14:58:29.583029

"""
import os
import pathlib
from datetime import datetime

import yaml
from alembic import op
from sqlalchemy import Column, Integer, BigInteger, ForeignKey, Text, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound  # noqa

from wrolpi import dates
from wrolpi.common import escape_file_name, get_media_directory, ModelHelper
from wrolpi.common import get_relative_to_media_directory
from wrolpi.dates import TZDateTime
from wrolpi.tags import get_tags_config

# revision identifiers, used by Alembic.
revision = '2bfb3b50b178'
down_revision = '8d0d81bc9c34'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False

Base = declarative_base()


class MFileGroup(ModelHelper, Base):
    __tablename__ = 'file_group'
    id: int = Column(BigInteger, primary_key=True)
    primary_path: pathlib.Path = Column(String, unique=True, nullable=False)


class MTagFile(ModelHelper, Base):
    __tablename__ = 'tag_file'
    tag_id = Column(Integer, ForeignKey('tag.id', ondelete='CASCADE'), primary_key=True)
    file_group_id = Column(BigInteger, ForeignKey('file_group.id', ondelete='CASCADE'), primary_key=True)


class MTag(ModelHelper, Base):
    __tablename__ = 'tag'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    color = Column(String)


class MZim(Base):
    __tablename__ = 'zim'
    id = Column(Integer, primary_key=True)
    path: pathlib.Path = Column(String, unique=True, nullable=False)


class MTagZimEntry(Base):
    __tablename__ = 'tag_zim'
    tag_id = Column(Integer, ForeignKey('tag.id', ondelete='CASCADE'), primary_key=True)
    zim_id = Column(Integer, ForeignKey('zim.id', ondelete='CASCADE'), primary_key=True)
    zim_entry: str = Column(Text, nullable=False, primary_key=True)
    created_at: datetime = Column(TZDateTime, default=dates.now)


def save_tags(session: Session):
    media_directory = get_media_directory()

    tags = dict()
    tag_rows = session.query(MTag)
    for tag in tag_rows:
        tags[tag.name] = dict(color=tag.color)

    results = session.query(MTag, MTagFile, MFileGroup) \
        .filter(MTagFile.tag_id == MTag.id, MTagFile.file_group_id == MFileGroup.id) \
        .order_by(MFileGroup.primary_path)

    tag_files = []
    for tag, tag_file, file_group in results:
        value = [
            tag.name,
            str(file_group.primary_path.relative_to(media_directory)),
            # Fallback to current time if not set.
            tag_file.created_at.isoformat() if tag_file.created_at else dates.now().isoformat(),
        ]
        tag_files.append(value)

    results = session.query(MTag, MZim, MTagZimEntry) \
        .filter(MTag.id == MTagZimEntry.tag_id, MZim.id == MTagZimEntry.zim_id) \
        .order_by(MTagZimEntry.zim_id, MTagZimEntry.zim_entry)

    tag_zims = []
    for tag, zim, tag_zim_entry in results:
        zim: MZim
        tag_zim_entry: MTagZimEntry
        value = [
            tag.name,
            str(get_relative_to_media_directory(zim.path)),
            tag_zim_entry.zim_entry,
            # Fallback to current time if not set.
            tag_zim_entry.created_at.isoformat() if tag_zim_entry.created_at else dates.now().isoformat(),
        ]
        tag_zims.append(value)

    # Write to the config.
    with get_tags_config().get_file().open('wt') as fh:
        data = {
            'tag_files': tag_files,
            'tag_zims': tag_zims,
            'tags': tags,
        }
        yaml.dump(data, fh)


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    need_commit = False
    tags = session.query(MTag).all()
    for tag in tags:
        escaped_name = escape_file_name(tag.name)
        if escaped_name != tag.name:
            tag.name = escaped_name
            session.flush([tag, ])
            need_commit = True

    if need_commit:
        session.commit()
        save_tags(session)


def downgrade():
    pass
