import pathlib
from typing import Union

from sqlalchemy import types

from wrolpi.common import get_media_directory

PATH_TYPE = Union[str, pathlib.Path]


class MediaPath:
    """
    Enforce that a given path is within the Media Directory.
    """

    def __init__(self, path: PATH_TYPE):
        path = self._validate_path(path)
        self._path = path.absolute()

    def __repr__(self):
        return f'<MediaPath path={self.path}>'

    @classmethod
    def _validate_path(cls, path: PATH_TYPE):
        if not path:
            raise ValueError(f'Path must not be empty!')

        path = pathlib.Path(path) if not isinstance(path, pathlib.Path) else path
        if not path.is_absolute():
            # Assume the path is relative to the media directory.
            path = get_media_directory() / path
        elif not path.is_relative_to(get_media_directory()):
            # Absolute paths must be within the media directory.
            raise ValueError(f'Path {path} must be in {get_media_directory()}')

        return path

    def __json__(self):
        # Always return a relative path to frontend.
        return str(self.path.relative_to(get_media_directory()))

    @property
    def path(self) -> pathlib.Path:
        return self._path

    @path.setter
    def path(self, path: PATH_TYPE):
        path = self._validate_path(path)
        self._path = path.absolute()

    def __eq__(self, other):
        return self._path == other


class MediaPathType(types.TypeDecorator):  # noqa
    impl = types.String

    def process_bind_param(self, value, dialect):
        return str(value) if value else None

    def process_result_value(self, value, dialect):
        if value:
            return MediaPath(value)
