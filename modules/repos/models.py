import pathlib
from typing import Optional

from sqlalchemy import Column, Integer, String, ForeignKey, BigInteger, Text, Boolean, false
from sqlalchemy.orm import relationship, Session, joinedload, selectinload, deferred

from wrolpi.collections.models import Collection
from wrolpi.common import Base, ModelHelper, get_relative_to_media_directory
from wrolpi.dates import TZDateTime
from wrolpi.db import serializer
from wrolpi.downloader import Download
from .errors import UnknownRepo

__all__ = ['Repository', 'REPO_MODES']

# full: every branch and tag, with all history.  snapshot: only the latest commit of one branch.
REPO_MODES = ('full', 'snapshot')


class Repository(ModelHelper, Base):
    """A git repository mirrored into a `kind='repo'` Collection's directory.

    The name, directory and Tag live on the Collection; the Collection's recurring Download keeps the mirror
    up to date."""
    __tablename__ = 'repository'
    id = Column(Integer, primary_key=True)
    # The https clone URL; unique (compared without a trailing `.git`, see `repo_url_key`).
    url = Column(String, nullable=False, unique=True)
    host = Column(String)
    owner = Column(String)
    mode = Column(String, nullable=False, default='full')
    # The branch to check out; None follows the remote's default branch.
    branch = Column(String)
    # Random; written in the clone's .git (see lib.mark_clone).  Only a clone holding it is updated, so a clone which
    # WROLPi did not make for this Repo is never reset or cleaned.
    clone_token = Column(String)
    # Also download the repo's submodules.
    submodules = Column(Boolean, nullable=False, default=False, server_default=false())
    default_branch = Column(String)
    head_sha = Column(String)
    head_date = Column(TZDateTime)
    head_message = Column(Text)
    last_fetch = Column(TZDateTime)
    size = Column(BigInteger)
    # The README in the repo's root directory, relative to the repo.
    readme_path = Column(String)
    # Searched by `repository_fts` (see wrolpi.fts); kept current by `update_search_name` and the downloader.
    search_name = Column(String)
    readme_text = deferred(Column(Text))

    collection_id = Column(Integer, ForeignKey('collection.id', ondelete='CASCADE'), nullable=False, unique=True)
    # Joined: a Repository's name, directory and Tag live on its Collection.
    collection = relationship('Collection', foreign_keys=[collection_id], lazy='joined')
    # The Download of this Repo's URL: its recurring Download, or the one-time Download of a Repo which is never
    # updated (which cannot belong to its Collection).
    url_download = relationship('Download', primaryjoin='Repository.url == foreign(Download.url)', viewonly=True,
                                uselist=False)

    def __repr__(self):
        return f'<Repository id={self.id} url={self.url} directory={self.directory}>'

    @property
    def name(self) -> Optional[str]:
        return self.collection.name if self.collection else None

    @property
    def directory(self) -> Optional[pathlib.Path]:
        return self.collection.directory if self.collection else None

    @property
    def tag_name(self) -> Optional[str]:
        return self.collection.tag_name if self.collection else None

    @property
    def download(self) -> Optional[Download]:
        """The recurring Download which keeps this repo up to date."""
        downloads = [i for i in self.collection.downloads if i.frequency] if self.collection else []
        return downloads[0] if downloads else None

    @property
    def once_download(self) -> Optional[Download]:
        """The one-time Download which clones (or updates, on request) a Repo which is never updated."""
        download = self.url_download
        return download if download and not download.frequency else None

    def update_search_name(self):
        """The Repo is found by its name and its owner."""
        self.search_name = ' '.join(i for i in (self.name, self.owner) if i)

    @property
    def location(self) -> str:
        return f'/repos/{self.id}'

    @staticmethod
    def json_options() -> tuple:
        """Loader options for a query whose Repositories will be serialized."""
        return (
            joinedload(Repository.collection).joinedload(Collection.tag),
            joinedload(Repository.collection).selectinload(Collection.downloads).defer(Download.info_json),
            selectinload(Repository.url_download).defer(Download.info_json),
        )

    @serializer
    def __json__(self) -> dict:
        download = self.download
        # The status of the last update; a Repo which is never updated is only updated on request.
        latest = download or self.once_download
        return {
            'id': self.id,
            'collection_id': self.collection_id,
            'name': self.name,
            'description': self.collection.description if self.collection else None,
            'directory': str(get_relative_to_media_directory(self.directory)) if self.directory else None,
            'tag_name': self.tag_name,
            'url': self.url,
            'host': self.host,
            'owner': self.owner,
            'mode': self.mode,
            'branch': self.branch,
            'submodules': self.submodules,
            'default_branch': self.default_branch,
            'head_sha': self.head_sha,
            'head_date': self.head_date,
            'head_message': self.head_message,
            'last_fetch': self.last_fetch,
            'size': self.size,
            'readme_path': self.readme_path,
            'location': self.location,
            # 0: never updated.
            'frequency': download.frequency if download else 0,
            'download_id': latest.id if latest else None,
            'download_status': latest.status if latest else None,
            'download_error': latest.error if latest else None,
            'next_download': download.next_download if download else None,
        }

    @staticmethod
    def find_by_id(session: Session, id_: int, options: tuple = ()) -> 'Repository':
        repo = session.query(Repository).options(*options).filter_by(id=id_).one_or_none()
        if not repo:
            raise UnknownRepo(f'Cannot find repo with id {id_}')
        return repo

    @staticmethod
    def get_by_collection_id(session: Session, collection_id: int) -> Optional['Repository']:
        return session.query(Repository).filter_by(collection_id=collection_id).one_or_none()
