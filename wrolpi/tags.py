import contextlib
from typing import List

from sqlalchemy import Column, Integer, String, ForeignKey, BigInteger
from sqlalchemy.orm import relationship, Session

from wrolpi.common import ModelHelper, Base, logger, ConfigFile, get_media_directory
from wrolpi.db import optional_session
from wrolpi.errors import UnknownTag, UsedTag

logger = logger.getChild(__name__)


class TagFile(ModelHelper, Base):
    __tablename__ = 'tag_file'

    tag_id = Column(Integer, ForeignKey('tag.id', ondelete='CASCADE'), primary_key=True)
    tag = relationship('Tag', back_populates='tag_files')
    file_group_id = Column(BigInteger, ForeignKey('file_group.id', ondelete='CASCADE'), primary_key=True)
    file_group = relationship('FileGroup', back_populates='tag_files')


class Tag(ModelHelper, Base):
    __tablename__ = 'tag'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    color = Column(String)

    tag_files = relationship('TagFile', back_populates='tag', cascade='all')

    def __repr__(self):
        name = self.name
        color = self.color
        return f'<Tag {name=} {color=}>'

    def __json__(self):
        return dict(
            id=self.id,
            name=self.name,
            color=self.color,
        )

    @optional_session
    def add_tag(self, file_group, session: Session = None) -> TagFile:
        """Add a TagFile for the provided FileGroup and this Tag.

        @warning: Commits the session to keep the config in sync."""
        from wrolpi.files.models import FileGroup
        if not isinstance(file_group, FileGroup):
            raise ValueError('Cannot apply tag to non-FileGroup')

        tag_file = TagFile(file_group_id=file_group.id, tag_id=self.id)
        logger.info(f'Tagging {file_group} with {self}')
        session.add(tag_file)
        session.flush([tag_file])
        get_tags_config().add_tag(tag_file)
        session.commit()
        return tag_file

    @optional_session
    def remove_tag(self, file_group, session: Session = None):
        """Remove the record of a Tag applied to the FileGroup.

        @warning: Commits the session to keep config in sync."""
        from wrolpi.files.models import FileGroup
        if not isinstance(file_group, FileGroup):
            raise ValueError('Cannot remove tag of non-FileGroup')

        tag_file = session.query(TagFile) \
            .filter(TagFile.file_group_id == file_group.id, TagFile.tag_id == self.id) \
            .one_or_none()
        if tag_file:
            session.delete(tag_file)
            get_tags_config().remove_tag(tag_file)
            session.commit()
        else:
            logger.warning(f'Could not find tag_file for FileGroup.id={file_group.id}/Tag.id={self.id=}')

    @staticmethod
    @optional_session
    def find_by_name(name: str, session: Session) -> 'Tag':
        tag = session.query(Tag).filter_by(name=name).one_or_none()
        return tag


class TagsConfig(ConfigFile):
    file_name = 'tags.yaml'

    default_config = dict(
        tags=list(),
    )

    @property
    def tags(self) -> list:
        return self._config['tags']

    @tags.setter
    def tags(self, value):
        self.update({'tags': value})

    def add_tag(self, tag_file: TagFile):
        from wrolpi.files.models import FileGroup
        file_group: FileGroup = tag_file.file_group
        primary_path = str(file_group.primary_path.relative_to(get_media_directory()))
        tag_name = tag_file.tag.name
        tags = self.tags.copy()

        value = [primary_path, tag_name]
        if value not in tags:
            tags.append(value)
            self.tags = tags

    def remove_tag(self, tag_file: TagFile):
        from wrolpi.files.models import FileGroup
        file_group: FileGroup = tag_file.file_group
        primary_path = str(file_group.primary_path.relative_to(get_media_directory()))
        tag_name = tag_file.tag.name
        tags = self.tags.copy()

        for idx, value in enumerate(self.tags):
            if value == [primary_path, tag_name]:
                tags = tags.copy()
                tags.pop(idx)
                self.tags = tags
                break


TAGS_CONFIG: TagsConfig = TagsConfig(global_=True)
TEST_TAGS_CONFIG: TAGS_CONFIG = None


def get_tags_config():
    global TEST_TAGS_CONFIG
    if isinstance(TEST_TAGS_CONFIG, ConfigFile):
        return TEST_TAGS_CONFIG

    global TAGS_CONFIG
    return TAGS_CONFIG


@contextlib.contextmanager
def test_tags_config():
    global TEST_TAGS_CONFIG
    TEST_TAGS_CONFIG = TagsConfig()
    yield
    TEST_TAGS_CONFIG = None


@optional_session
def get_tags(session: Session) -> List[Tag]:
    tags = list(session.query(Tag))
    return tags


@optional_session
def new_tag(name: str, color: str, session: Session) -> Tag:
    tag = Tag(name=name, color=color)
    session.add(tag)
    session.flush([tag])
    session.commit()
    return tag


@optional_session
def delete_tag(name: str, session: Session = None):
    tag: Tag = Tag.find_by_name(name, session)
    if not tag:
        raise UnknownTag(f'Cannot find tag {name}')
    if tag.tag_files:
        count = len(tag.tag_files)
        raise UsedTag(f'Cannot delete {name} it is used by {count} files!')

    session.delete(tag)
    session.commit()
