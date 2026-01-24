import pathlib
from typing import Union

from sqlalchemy import types

PATH_TYPE = Union[str, pathlib.Path]


class MediaPathType(types.TypeDecorator):  # noqa
    impl = types.String

    def process_bind_param(self, value, dialect):
        """Convert paths into what the DB expects. (pathlib.Path -> str)"""
        if value is None:
            return value

        if value == '':
            raise ValueError('MediaPath cannot be empty')

        if isinstance(value, pathlib.Path):
            if not value.is_absolute():
                # Resolve relative paths against media directory, not cwd
                from wrolpi.common import get_media_directory
                value = get_media_directory() / value
            value = str(value)

        if not isinstance(value, str):
            raise ValueError(f'Invalid MediaPath type ({type(value)}): {value}')

        return value

    def process_result_value(self, value, dialect):
        if value:
            return pathlib.Path(value)
