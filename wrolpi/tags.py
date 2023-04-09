import contextlib
from typing import List, Dict

from sqlalchemy import Column, Integer, String, ForeignKey, BigInteger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import relationship, Session

from wrolpi.common import ModelHelper, Base, logger, ConfigFile, get_media_directory, background_task, run_after, \
    limit_concurrent
from wrolpi.db import optional_session
from wrolpi.errors import UnknownTag, UsedTag, InvalidTag
from wrolpi.vars import PYTEST

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
    def add_file_group_tag(self, file_group, session: Session = None) -> TagFile:
        """Add a TagFile for the provided FileGroup and this Tag.

        @warning: Commits the session to keep the config in sync."""
        from wrolpi.files.models import FileGroup
        if not isinstance(file_group, FileGroup):
            raise ValueError('Cannot apply tag to non-FileGroup')

        tag_file = TagFile(file_group_id=file_group.id, tag_id=self.id)
        logger.info(f'Tagging {file_group} with {self}')
        session.add(tag_file)
        session.flush([tag_file])
        session.commit()

        # Save changes to config.
        schedule_save(session)
        return tag_file

    @optional_session
    def remove_file_group_tag(self, file_group, session: Session = None):
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
            session.commit()

            # Save changes to config.
            schedule_save(session)
        else:
            logger.warning(f'Could not find tag_file for FileGroup.id={file_group.id}/Tag.id={self.id=}')

    @staticmethod
    @optional_session
    def find_by_name(name: str, session: Session) -> 'Tag':
        tag = session.query(Tag).filter_by(name=name).one_or_none()
        return tag


class TagsConfig(ConfigFile):
    file_name = 'tags.yaml'
    width = 500

    default_config = dict(
        tag_files=list(),
        tags=list(),
    )

    @property
    def tag_files(self) -> list:
        return self._config['tag_files']

    @tag_files.setter
    def tag_files(self, value):
        value = sorted(value, key=lambda i: (i[0].lower(), i[1]))
        self.update({'tag_files': value})

    @property
    def tags(self) -> dict:
        return self._config['tags']

    @tags.setter
    def tags(self, value: dict):
        self.update({'tags': value})

    def save_tags(self, session: Session):
        media_directory = get_media_directory()

        tags = dict()
        tag_rows = session.query(Tag)
        for tag in tag_rows:
            tags[tag.name] = dict(color=tag.color)

        from wrolpi.files.models import FileGroup
        results = session.query(Tag, TagFile, FileGroup) \
            .filter(TagFile.tag_id == Tag.id, TagFile.file_group_id == FileGroup.id) \
            .order_by(FileGroup.primary_path)

        tag_files = []
        for tag, _, file_group in results:
            value = [tag.name, str(file_group.primary_path.relative_to(media_directory))]
            tag_files.append(value)

        # Write to the config.
        self.update({
            'tag_files': tag_files,
            'tags': tags,
        })


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
def schedule_save(session: Session = None):
    """Schedule a background task to save all TagFiles to the config file.  If testing, save synchronously."""
    if PYTEST:
        get_tags_config().save_tags(session)
    else:
        async def _():
            get_tags_config().save_tags(session)

        background_task(_())


@optional_session
def get_tags(session: Session) -> List[Tag]:
    tags = list(session.query(Tag).order_by(Tag.name))
    return tags


@optional_session
@run_after(schedule_save)
def upsert_tag(name: str, color: str, tag_id: int = None, session: Session = None) -> Tag:
    if ',' in name:
        raise InvalidTag('Tag name cannot have comma')

    if tag_id:
        tag = session.query(Tag).filter_by(id=tag_id).one_or_none()
        if not tag:
            raise UnknownTag(f'Cannot find tag with id={tag_id}')
        tag.name = name
        tag.color = color
    else:
        tag = Tag(name=name, color=color)
        session.add(tag)

    try:
        session.flush([tag])
        session.commit()
    except IntegrityError as e:
        # Conflicting name
        session.rollback()
        raise InvalidTag(f'Name already taken') from e

    schedule_save()

    return tag


@optional_session
def delete_tag(tag_id: int, session: Session = None):
    tag: Tag = session.query(Tag).filter_by(id=tag_id).one_or_none()

    if not tag:
        raise UnknownTag(f'Cannot find tag {tag_id}')

    if tag.tag_files:
        count = len(tag.tag_files)
        raise UsedTag(f'Cannot delete {tag.name} it is used by {count} files!')

    session.delete(tag)
    session.commit()

    schedule_save()


@optional_session
def import_tags_config(session: Session = None):
    """Reads the Tags and TagFiles from the config file, upserts them in the DB."""
    if PYTEST and not TEST_TAGS_CONFIG:
        logger.warning('Refusing to import tags without test tags config.  '
                       'Use `test_tags_config` fixture if you would like to call this.')
        return

    config = get_tags_config()
    if not (path := config.get_file()).is_file():
        logger.warning(f'Refusing to import tags config because it does not exist: {path}')
        return

    logger.info('Importing tags config')

    try:
        if config.tags:
            # Tags have been saved to config, import them
            tags_by_name: Dict[str, Tag] = {i.name: i for i in session.query(Tag)}
            new_tags = list()
            for name, attrs in config.tags.items():
                tag = tags_by_name.get(name)
                if not tag:
                    # Maintainer added a Tag to the config manually, or DB was wiped.
                    tag = Tag(name=name, color=attrs['color'])
                    new_tags.append(tag)
                tag.color = attrs['color']

            if new_tags:
                session.add_all(new_tags)

            session.commit()

        if config.tag_files:
            from wrolpi.files.models import FileGroup

            need_commit = False

            # Get all Tags again because new ones may exist.
            tags_by_name: Dict[str, Tag] = {i.name: i for i in session.query(Tag)}

            media_directory = get_media_directory()
            primary_paths = [str(media_directory / i[1]) for i in config.tag_files]
            file_groups = session.query(FileGroup).filter(FileGroup.primary_path.in_(primary_paths))
            file_groups_by_primary_path = {i.primary_path: i for i in file_groups}
            file_group_ids = [i.id for i in file_groups]
            # Get all TagFiles referencing the FileGroups.
            tag_files = session.query(TagFile).filter(TagFile.file_group_id.in_(file_group_ids))
            tag_files = [(i.tag_id, i.file_group_id) for i in tag_files]

            for tag_name, primary_path in config.tag_files:
                tag: Tag = tags_by_name.get(tag_name)
                # Paths are absolute in the DB, relative in config.
                absolute_path = media_directory / primary_path
                file_group: FileGroup = file_groups_by_primary_path.get(absolute_path)
                if tag and file_group:
                    if (tag.id, file_group.id) not in tag_files:
                        # This FileGroup has not been tagged with the Tag, add it.
                        tag.add_file_group_tag(file_group, session)
                        need_commit = True
                elif not file_group:
                    logger.warning(f'Cannot find FileGroup for {repr(str(primary_path))}')
                elif not tag:
                    logger.warning(f'Cannot find Tag for {repr(str(primary_path))}')

            if need_commit:
                session.commit()
    except Exception as e:
        logger.error(f'Failed to import tags config', exc_info=e)
        if PYTEST:
            raise
