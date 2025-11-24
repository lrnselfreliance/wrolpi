import asyncio
import atexit
import contextlib
import functools
import inspect
import json
import logging
import logging.config
import multiprocessing
import os
import pathlib
import re
import shutil
import socket
import string
import sys
import tempfile
from asyncio import Task
from copy import deepcopy
from dataclasses import dataclass, asdict, field, fields
from datetime import datetime, date
from decimal import Decimal
from functools import wraps
from itertools import islice, filterfalse, tee
from multiprocessing.managers import DictProxy
from pathlib import Path
from types import GeneratorType, MappingProxyType
from typing import Union, Callable, Tuple, Dict, List, Iterable, Optional, Generator, Any, Set
from urllib.parse import urlparse, urlunsplit

import aiohttp
import bs4
import yaml
from aiohttp import ClientResponse, ClientSession
from bs4 import BeautifulSoup
from selenium import webdriver
from sqlalchemy import types
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

from wrolpi.dates import now, from_timestamp
from wrolpi.errors import WROLModeEnabled, NativeOnly, LogLevelError, InvalidConfig, \
    ValidationError
from wrolpi.vars import PYTEST, DOCKERIZED, CONFIG_DIR, MEDIA_DIRECTORY, DEFAULT_HTTP_HEADERS


def add_logging_level(level_name: str, level_int: int, methodName=None):
    """
    Comprehensively adds a new logging level to the `logging` module and the
    currently configured logging class.

    `levelName` becomes an attribute of the `logging` module with the value
    `levelNum`. `methodName` becomes a convenience method for both `logging`
    itself and the class returned by `logging.getLoggerClass()` (usually just
    `logging.Logger`). If `methodName` is not specified, `levelName.lower()` is
    used.

    To avoid accidental clobberings of existing attributes, this method will
    raise an `AttributeError` if the level name is already an attribute of the
    `logging` module or if the method name is already present

    Example
    -------
    >>> add_logging_level('TRACE', logging.DEBUG - 5)
    >>> logging.getLogger(__name__).setLevel("TRACE")
    >>> logging.getLogger(__name__).trace('that worked')
    >>> logging.trace('so did this')
    >>> logging.TRACE
    5

    This function is taken directly from: https://stackoverflow.com/questions/2183233/how-to-add-a-custom-loglevel-to-pythons-logging-facility/35804945#35804945
    """
    if not methodName:
        methodName = level_name.lower()

    if hasattr(logging, level_name):
        raise AttributeError('{} already defined in logging module'.format(level_name))
    if hasattr(logging, methodName):
        raise AttributeError('{} already defined in logging module'.format(methodName))
    if hasattr(logging.getLoggerClass(), methodName):
        raise AttributeError('{} already defined in logger class'.format(methodName))

    # This method was inspired by the answers to Stack Overflow post
    # http://stackoverflow.com/q/2183233/2988730, especially
    # http://stackoverflow.com/a/13638084/2988730
    def logForLevel(self, message, *args, **kwargs):
        if self.isEnabledFor(level_int):
            kwargs.setdefault('stacklevel', 3)
            self._log(level_int, message, args, **kwargs)

    def logToRoot(message, *args, **kwargs):
        kwargs.setdefault('stacklevel', 3)
        logging.log(level_int, message, *args, **kwargs)

    logging.addLevelName(level_int, level_name)
    setattr(logging, level_name, level_int)
    setattr(logging.getLoggerClass(), methodName, logForLevel)
    setattr(logging, methodName, logToRoot)


LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'loggers': {
        'sanic.root': {
            'level': 'INFO',
            'handlers': ['console'],
        },
        'sanic.error': {
            'level': 'INFO',
            'handlers': ['error_console'],
            'qualname': 'sanic.error',
        },
        'sanic.access': {
            'level': 'INFO',
            'handlers': ['access_console'],
            'qualname': 'sanic.access',
        },
        'sanic.server': {
            'level': 'INFO',
            'handlers': ['console'],
            'qualname': 'sanic.server',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'generic',
            'stream': sys.stdout,
            'filters': ['empty_message_filter'],
        },
        'error_console': {
            'class': 'logging.StreamHandler',
            'formatter': 'generic',
            'stream': sys.stderr,
        },
        'access_console': {
            'class': 'logging.StreamHandler',
            'formatter': 'access',
            'stream': sys.stdout,
            'filters': ['empty_message_filter'],
        },
    },
    'formatters': {
        'generic': {
            'format': '[%(asctime)s] [%(process)d] [%(name)s:%(lineno)d] [%(levelname)s] %(message)s',
            'class': 'logging.Formatter',
        },
        'access': {
            'format': '[%(asctime)s] [%(process)d] [%(name)s:%(lineno)d] [%(levelname)s]: '
                      + '%(request)s %(message)s %(status)s %(byte)s',
            'class': 'logging.Formatter',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': logging.DEBUG
    },
    'filters': {
        'empty_message_filter': {
            '()': 'wrolpi.logging_extra.EmptyMessageFilter',
        }
    }
}


# Used so IDE will suggest `logger.trace`
class TraceLogger(logging.Logger):
    def trace(self, msg, *args, **kwargs):
        return self.log(TRACE_LEVEL, msg, *args, **kwargs)


# Apply logging config.
logger: TraceLogger = logging.getLogger()  # noqa Not really a TraceLogger, but I wanted IDE suggestions.
logging.config.dictConfig(LOGGING_CONFIG)

# Add extra verbose debug level (-vvv)
TRACE_LEVEL = logging.DEBUG - 5
if not hasattr(logging, 'TRACE'):
    add_logging_level('TRACE', TRACE_LEVEL)

logger_ = logger.getChild(__name__)


def set_log_level(level: int, warn_level: bool = True):
    """Set the level of the root logger so all children that have been created (or will be created) share the same
    level.

    @warning: Child processes will not share this level.  See set_global_log_level
    """
    logger.setLevel(level)
    logger_.setLevel(level)

    # Always warn about the log level, so we know what should have been logged.
    effective_level = logger.getEffectiveLevel()
    level_name = logging.getLevelName(effective_level)
    if warn_level:
        logger.warning(f'Logging level: {level_name}')

    # Change log level for all handlers.
    for handler in logger.handlers:
        handler.setLevel(level)

    # Enable debug logging in SQLAlchemy when logging is TRACE.
    sa_logger = logging.getLogger('sqlalchemy.engine')
    sa_level = logging.DEBUG if level == TRACE_LEVEL else logging.WARNING
    sa_logger.setLevel(logging.NOTSET)

    # Hide sanic access logs when not at least "INFO".
    sanic_access = logging.getLogger('sanic.access')
    sanic_level = logging.INFO if level <= 20 else logging.WARNING
    sanic_access.setLevel(sanic_level)


def set_global_log_level(log_level: int):
    """Set the global (shared between processes) log level."""
    if not isinstance(log_level, int) or not 0 <= log_level <= 40:
        raise LogLevelError()
    from wrolpi.api_utils import api_app
    with api_app.shared_ctx.log_level.get_lock():
        api_app.shared_ctx.log_level.value = log_level


@contextlib.contextmanager
def log_level_context(level):
    starting_level = logger.getEffectiveLevel()
    set_log_level(level, warn_level=False)
    yield
    set_log_level(starting_level, warn_level=False)


__all__ = [
    'Base',
    'ConfigFile',
    'DownloadFileInfo',
    'LOGGING_CONFIG',
    'ModelHelper',
    'TRACE_LEVEL',
    'WROLPI_CONFIG',
    'aiohttp_get',
    'aiohttp_head',
    'aiohttp_post',
    'api_param_limiter',
    'apply_modelers',
    'apply_refresh_cleanup',
    'background_task',
    'can_connect_to_server',
    'cancel_background_tasks',
    'cancel_refresh_tasks',
    'cancelable_wrapper',
    'chain',
    'chdir',
    'check_media_directory',
    'chunks',
    'chunks_by_stem',
    'compile_tsvector',
    'create_empty_config_files',
    'cum_timer',
    'date_range',
    'disable_wrol_mode',
    'enable_wrol_mode',
    'escape_file_name',
    'extract_domain',
    'extract_headlines',
    'extract_html_text',
    'format_html_string',
    'format_json_file',
    'get_absolute_media_path',
    'get_all_configs',
    'get_download_info',
    'get_files_and_directories',
    'get_global_statistics',
    'get_html_soup',
    'get_media_directory',
    'get_relative_to_media_directory',
    'get_title_from_html',
    'get_warn_once',
    'get_wrolpi_config',
    'html_screenshot',
    'insert_parameter',
    'iterify',
    'limit_concurrent',
    'logger',
    'make_media_directory',
    'minimize_dict',
    'native_only',
    'partition',
    'recursive_map',
    'register_modeler',
    'register_refresh_cleanup',
    'remove_whitespace',
    'replace_file',
    'resolve_generators',
    'run_after',
    'set_global_log_level',
    'set_log_level',
    'set_test_config',
    'set_test_media_directory',
    'slow_logger',
    'split_lines_by_length',
    'timer',
    'trim_file_name',
    'truncate_generator_bytes',
    'truncate_object_bytes',
    'tsvector',
    'unique_by_predicate',
    'url_strip_host',
    'walk',
    'wrol_mode_check',
    'wrol_mode_enabled',
    'zig_zag',
]

# Base is used for all SQLAlchemy models.
Base = declarative_base()


class ModelHelper:

    def dict(self, *_, **__) -> dict:
        d = {i.name: getattr(self, i.name) for i in self.__table__.columns}  # noqa
        return d

    @classmethod
    def upsert(cls, file, session: Session) -> Base:
        raise NotImplementedError('This model has not defined this method.')

    @staticmethod
    def get_by_path(path, session) -> Base:
        raise NotImplementedError('This model has not defined this method.')

    @staticmethod
    def get_by_id(id_: int, session: Session = None) -> Optional[Base]:
        """Attempts to get a model instance by its id.  Returns None if no instance can be found."""
        raise NotImplementedError('This model has not defined this method.')

    @staticmethod
    def find_by_id(id_: int, session: Session = None) -> Base:
        """Get a model instance by its id, raise an error if no instance is found."""
        raise NotImplementedError('This model has not defined this method.')

    @staticmethod
    def can_model(file_group) -> bool:
        raise NotImplementedError('This model has not defined this method.')

    @staticmethod
    def do_model(file_group, session: Session):
        raise NotImplementedError('This model has not defined this method.')

    def flush(self, session: Session = None):
        """A convenience method which flushes this record using its DB Session."""
        session = session or Session.object_session(self)
        if session:
            session.flush([self])
        else:
            raise RuntimeError(f'{self} is not in a session!')


class tsvector(types.TypeDecorator):
    impl = types.UnicodeText


@compiles(tsvector, 'postgresql')
def compile_tsvector(element, compiler, **kw):
    return 'tsvector'


URL_CHARS = string.ascii_lowercase + string.digits


def find_file(directory: pathlib.Path, name: str, depth=1) -> Optional[pathlib.Path]:
    """Recursively searches a directory for a
    file with the provided name."""
    if depth == 0:
        return

    for path in sorted(directory.iterdir()):
        if path.is_file() and path.name == name:
            return path
        if path.is_dir() and (result := find_file(path, name, depth - 1)):
            return result


TEST_MEDIA_DIRECTORY = None


def set_test_media_directory(path):
    global TEST_MEDIA_DIRECTORY
    if isinstance(path, pathlib.Path):
        TEST_MEDIA_DIRECTORY = path
    elif path:
        TEST_MEDIA_DIRECTORY = pathlib.Path(path)
    else:
        TEST_MEDIA_DIRECTORY = None


def is_tempfile(path: pathlib.Path | str) -> bool:
    path = str(path)
    if path.startswith('/tmp'):
        return True
    elif path.startswith('/var/folders/'):
        return True
    elif path.startswith('/private/var/folders/'):
        return True
    return False


def get_media_directory() -> Path:
    """Get the media directory.

    This will typically be /media/wrolpi, or something else from the .env.

    During testing, this function returns TEST_MEDIA_DIRECTORY.
    """
    global TEST_MEDIA_DIRECTORY

    if PYTEST and not TEST_MEDIA_DIRECTORY:
        raise RuntimeError('No test media directory set during testing!!')

    if isinstance(TEST_MEDIA_DIRECTORY, pathlib.Path):
        if not is_tempfile(TEST_MEDIA_DIRECTORY):
            raise RuntimeError(f'Refusing to run test outside tmp directory: {TEST_MEDIA_DIRECTORY}')
        return TEST_MEDIA_DIRECTORY.resolve()

    return MEDIA_DIRECTORY


class ConfigFile:
    """
    This is used to keep the DB and config files in sync.  Importing the config reads the config from file, then
    applies it to this config instance, AND the database.  Dumping the config copies data from the database and saves it
    to the config file.  Updating this config is automatically saved to the config file.

    Configs cannot be saved until they are imported without error.
    """
    background_dump: callable = None
    background_save: callable = None
    default_config: dict = None
    file_name: str = None
    validator: dataclass = None
    width: int = None

    def __init__(self):
        self.width = self.width or 90

        # Do not load a global config on import while testing.  A global instance should never be used for testing.
        self._config = deepcopy({k: v for k, v in self.default_config.items()})

        if self._config['version'] != 0:
            raise RuntimeError('Configs should start at version 0')

        from wrolpi.switches import register_switch_handler

        @register_switch_handler(f'background_save_{self.file_name}')
        def background_save(overwrite: bool = False):
            self.save(overwrite=overwrite)

        self.background_save = background_save

        @register_switch_handler(f'background_dump_{self.file_name}')
        def background_dump(file: pathlib.Path = None):
            self.dump_config(file)

        self.background_dump = background_dump

    def __repr__(self):
        return f'<{self.__class__.__name__} file={self.get_file()}>'

    def config_status(self) -> dict:
        d = dict(
            file_name=self.file_name,
            rel_path=get_relative_to_media_directory(self.get_file()),
            successful_import=self.successful_import,
            valid=self.is_valid(),
        )
        return d

    def __json__(self) -> dict:
        return dict(self._config)

    def initialize(self, multiprocessing_dict: Optional[DictProxy] = None):
        """Initializes this config dict using the default config and the config file."""
        # Use the provided multiprocessing.Manager().dict() when live, or, dict() for testing.
        self._config = multiprocessing_dict if multiprocessing_dict is not None else dict()
        # Use the default settings to initialize the config.
        self._config.update(deepcopy(self.default_config))

        file = self.get_file()
        if file.is_file():
            if not self.is_valid(file):
                raise InvalidConfig(f'Config file is invalid: {str(self.get_relative_file())}')
            config_data = self.read_config_file(file)
            config_data = {k: v for k, v in config_data.items() if k in self.default_config}
            self._config.update(asdict(self.validator(**config_data)))
        return self

    @property
    def successful_import(self) -> bool:
        from wrolpi.api_utils import api_app
        return bool(api_app.shared_ctx.configs_imported.get(self.file_name))

    @successful_import.setter
    def successful_import(self, value: bool):
        from wrolpi.api_utils import api_app
        api_app.shared_ctx.configs_imported[self.file_name] = value

    def read_config_file(self, file: pathlib.Path = None) -> dict:
        file = file or self.get_file()
        with file.open('rt') as fh:
            config_data = yaml.load(fh, Loader=yaml.Loader)
            if not isinstance(config_data, dict):
                raise InvalidConfig(f'Config file is invalid: {file}')
            return config_data

    def _get_backup_filename(self):
        """Returns the path for the backup file for today."""
        # TODO what if the RPi clock is not working?  Change this so the "version" of the config is used each day.
        path = get_media_directory() / f'config/backup/{self.file_name}'
        date_str = now().strftime('%Y%m%d')
        name = f'{path.stem}-{date_str}{path.suffix}'
        path = path.with_name(name)
        return path

    def save(self, file: pathlib.Path = None, send_events: bool = False, overwrite: bool = False):
        """
        Write this config to its file.

        @param file: The destination of the config file (defaults to `self.get_file()`).
        @param send_events: Send failure Events to UI.
        @param overwrite: Will overwrite the config file even if it was not imported successfully.
        """
        from wrolpi.api_utils import api_app
        from wrolpi.events import Events

        file = file or self.get_file()
        if self.file_name not in file.name:
            raise RuntimeError(f'Refusing to save config to file which does not match {self.__class__.__name__}')

        rel_path = get_relative_to_media_directory(file)

        if file.exists() and overwrite is False:
            if not self.successful_import:
                Events.send_config_save_failed(f'Failed to save config: {rel_path}')
                raise RuntimeError(f'Refusing to save config because it was never successfully imported! {rel_path}')
            version = self.read_config_file(file).get('version')
            if version and version > self.version:
                raise RuntimeError(f'Refusing to overwrite newer config ({rel_path}): {version} > {self.version}')

        # Don't overwrite a real config while testing.
        if PYTEST and not is_tempfile(file):
            raise ValueError(f'Refusing to save config file while testing: {rel_path}')

        logger_.debug(f'Save config called for {rel_path}')

        # Only one process can write to a config.
        with api_app.shared_ctx.config_save_lock:
            try:
                # Config directory may not exist.
                if not file.parent.is_dir():
                    file.parent.mkdir()

                # Backup the existing config file.
                if file.is_file():
                    backup_file = self._get_backup_filename()
                    if not backup_file.parent.exists():
                        backup_file.parent.mkdir(parents=True)
                    shutil.copy(file, backup_file)
                    logger_.debug(f'Copied backup config: {rel_path} -> {backup_file}')

                # Write the config in-memory to the file.  Track version changes to avoid overriding newer config.
                self._config['version'] = (self._config['version'] or 0) + 1
                config = deepcopy(self._config)
                self.write_config_data(config, file)

                # Set successful_import in case this was the first time the config was written.
                self.successful_import = True

                logger_.info(f'Saved config: {rel_path}')
            except Exception as e:
                # Configs are vital, raise a big error when this fails.
                message = f'Failed to save config: {rel_path}'
                logger_.critical(message, exc_info=e)
                if send_events:
                    Events.send_config_save_failed(message)
                raise e

    def write_config_data(self, config: dict, config_file: pathlib.Path):
        with config_file.open('wt') as fh:
            yaml.dump(config, fh, width=self.width, sort_keys=True)
            # Wait for data to be written before releasing lock.
            fh.flush()
            os.fsync(fh.fileno())

    def get_file(self) -> Path:
        if not self.file_name:
            raise NotImplementedError(f'You must define a file name for this {self.__class__.__name__} config.')

        if PYTEST:
            return get_media_directory() / f'config/{self.file_name}'

        return CONFIG_DIR / self.file_name

    def get_relative_file(self):
        return get_relative_to_media_directory(self.get_file())

    def import_config(self, file: pathlib.Path = None, send_events=False):
        """Read config file data, apply it to the in-memory config and database."""
        file = file or self.get_file()
        file_str = str(get_relative_to_media_directory(file))
        # Caller will set to successful if it works.
        self.successful_import = False
        if file.is_file():
            if not self.is_valid(file):
                raise InvalidConfig(f'Config is invalid: {file_str}')

            data = self.read_config_file(file)
            new_data, extra_data = partition(lambda i: i[0] in self.default_config, data.items())
            new_data, extra_data = dict(new_data), dict(extra_data)
            if extra_data:
                logger_.warning(f'Ignoring extra config data ({file_str}): {extra_data}')
            self._config.update(new_data)
            # Import call above this will set successful_import.
            # self.successful_import = True
        else:
            logger_.error(f'Failed to import {file_str} because it does not exist.')

    def dump_config(self, file: pathlib.Path = None, send_events=False, overwrite=False):
        """Dump database data, copy it to this the in-memory config, then write it to the config file."""
        # Copy the data as-is by default.  Other classes will overwrite this and dump the database before saving.
        self.save(file, send_events, overwrite)

    def update(self, config: dict, overwrite: bool = False):
        """Update any values of this config.  Save the config to its file."""
        from wrolpi.api_utils import api_app
        if not self.validate(config):
            raise ValidationError(f'Invalid config: {config}')

        with api_app.shared_ctx.config_update_lock:
            config = {k: v for k, v in config.items() if k in self._config}
            self._config.update(config)
        self.background_save.activate_switch(context={'overwrite': overwrite})

    def dict(self) -> dict:
        """Get a deepcopy of this config."""
        if not hasattr(self, '_config'):
            raise NotImplementedError('You cannot use a global config while testing!')

        return deepcopy(self._config)

    def validate(self, config: dict) -> bool:
        allowed_fields = {i.name for i in fields(self.validator)}
        try:
            # Remove keys no longer in the config.
            config_items = config.items()
            extra_items = {k: v for k, v in config_items if k not in allowed_fields}
            if extra_items:
                logger.error(f'Invalid config items: {extra_items}')
            config = {k: v for k, v in config_items if k in allowed_fields}
            self.validator(**config)
            return True
        except Exception as e:
            logger.debug(f'Failed to validate config', exc_info=e)
            return False

    def is_valid(self, file: pathlib.Path = None) -> bool | None:
        if not self.validator:
            raise NotImplementedError(f'Cannot validate {self.file_name} without validator!')

        file = file or self.get_file()
        if not file.is_file() or file.stat().st_size == 0:
            return None

        try:
            config_data = self.read_config_file(file)
        except InvalidConfig:
            return False

        return self.validate(config_data)

    # `version` is used to prevent overwriting of newer configs.  Cannot not be modified directly.

    @property
    def version(self) -> int:
        return self._config['version']


@dataclass
class WROLPiConfigValidator:
    archive_destination: str = None
    download_on_startup: bool = None
    download_timeout: int = None
    hotspot_device: str = None
    hotspot_on_startup: bool = None
    hotspot_password: str = None
    hotspot_ssid: str = None
    ignore_outdated_zims: bool = None
    map_destination: str = None
    nav_color: str = None
    throttle_on_startup: bool = None
    version: int = None
    videos_destination: str = None
    wrol_mode: bool = None
    zims_destination: str = None
    ignored_directories: list[str] = field(default_factory=list)


def get_all_configs() -> Dict[str, ConfigFile]:
    all_configs = dict()

    if wrolpi_config := get_wrolpi_config():
        all_configs[wrolpi_config.file_name] = wrolpi_config

    from wrolpi.tags import get_tags_config
    if tags_config := get_tags_config():
        all_configs[tags_config.file_name] = tags_config

    from modules.videos.lib import get_channels_config
    if channels_config := get_channels_config():
        all_configs[channels_config.file_name] = channels_config

    from modules.inventory.common import get_inventories_config
    if inventories_config := get_inventories_config():
        all_configs[inventories_config.file_name] = inventories_config

    from modules.videos.lib import get_videos_downloader_config
    if videos_downloader_config := get_videos_downloader_config():
        all_configs[videos_downloader_config.file_name] = videos_downloader_config

    from wrolpi.downloader import get_download_manager_config
    if download_manager_config := get_download_manager_config():
        all_configs[download_manager_config.file_name] = download_manager_config

    return all_configs


def get_config_by_file_name(file_name: str) -> ConfigFile:
    configs = get_all_configs()
    if file_name not in configs:
        raise InvalidConfig(f'No config with {file_name} exists')

    return configs[file_name]


class WROLPiConfig(ConfigFile):
    file_name = 'wrolpi.yaml'
    default_config = dict(
        archive_destination='archive/%(domain)s',
        download_on_startup=True,
        download_timeout=0,
        hotspot_device='wlan0',
        hotspot_on_startup=True,
        hotspot_password='wrolpi hotspot',
        hotspot_ssid='WROLPi',
        ignore_outdated_zims=False,
        ignored_directories=['config', 'tags'],
        map_destination='map',
        nav_color='violet',
        throttle_on_startup=False,
        version=0,
        videos_destination='videos/%(channel_tag)s/%(channel_name)s',
        wrol_mode=False,
        zims_destination='zims',
    )
    validator = WROLPiConfigValidator

    def get_file(self) -> Path:
        """WROLPiConfig must be discovered so that other config files can be found."""
        if not self.file_name:
            raise NotImplementedError(f'You must define a file name for this {self.__class__.__name__} config.')

        if PYTEST:
            return get_media_directory() / f'config/{self.file_name}'

        # Use the usual "/media/wrolpi/config/wrolpi.yaml" if it exists.
        default_config_path = CONFIG_DIR / self.file_name
        if default_config_path.is_file():
            return default_config_path

        # Search the media directory for the special "wrolpi.yaml" file.  Assume the first one found is the config.
        # Use a depth of 3; multiple drives may exist and the config directory may be down in a second drive.
        if config_path := find_file(get_media_directory(), self.file_name, 3):
            return config_path

        # Not testing, and can't find file deep in media directory.  Use the default.
        return default_config_path

    def import_config(self, file: pathlib.Path = None, send_events=False):
        try:
            # WROLPiConfig does not sync to database.
            super().import_config(file)

            # Destinations cannot be empty.
            self._config['archive_destination'] = self.archive_destination or self.default_config['archive_destination']
            self._config['map_destination'] = self.map_destination or self.default_config['map_destination']
            self._config['videos_destination'] = self.videos_destination or self.default_config['videos_destination']
            self._config['zims_destination'] = self.zims_destination or self.default_config['zims_destination']

            self.successful_import = True
        except Exception as e:
            self.successful_import = False
            message = f'Failed to import {self.file_name}'
            logger.error(message, exc_info=e)
            if send_events:
                from wrolpi.events import Events
                Events.send_config_import_failed(message)
            raise

    @property
    def download_on_startup(self) -> bool:
        return self._config['download_on_startup']

    @download_on_startup.setter
    def download_on_startup(self, value: bool):
        self.update({'download_on_startup': value})

    @property
    def download_timeout(self) -> int:
        return self._config['download_timeout']

    @download_timeout.setter
    def download_timeout(self, value: int):
        self.update({'download_timeout': value})

    @property
    def hotspot_device(self) -> str:
        return self._config['hotspot_device']

    @hotspot_device.setter
    def hotspot_device(self, value: str):
        self.update({'hotspot_device': value})

    @property
    def hotspot_on_startup(self) -> bool:
        return self._config['hotspot_on_startup']

    @hotspot_on_startup.setter
    def hotspot_on_startup(self, value: bool):
        self.update({'hotspot_on_startup': value})

    @property
    def hotspot_password(self) -> str:
        return self._config['hotspot_password']

    @hotspot_password.setter
    def hotspot_password(self, value: str):
        self.update({'hotspot_password': value})

    @property
    def hotspot_ssid(self) -> str:
        return self._config['hotspot_ssid']

    @hotspot_ssid.setter
    def hotspot_ssid(self, value: str):
        self.update({'hotspot_ssid': value})

    @property
    def ignore_outdated_zims(self) -> bool:
        return self._config['ignore_outdated_zims']

    @ignore_outdated_zims.setter
    def ignore_outdated_zims(self, value: bool):
        self.update({'ignore_outdated_zims': value})

    @property
    def throttle_on_startup(self) -> bool:
        return self._config['throttle_on_startup']

    @throttle_on_startup.setter
    def throttle_on_startup(self, value: bool):
        self.update({'throttle_on_startup': value})

    @property
    def wrol_mode(self) -> bool:
        return self._config['wrol_mode']

    @wrol_mode.setter
    def wrol_mode(self, value: bool):
        self.update({'wrol_mode': value})

    @property
    def ignored_directories(self) -> List[str]:
        return self._config['ignored_directories']

    @ignored_directories.setter
    def ignored_directories(self, value: List[str]):
        self.update({'ignored_directories': value})

    @property
    def videos_destination(self) -> str:
        return self._config['videos_destination']

    @videos_destination.setter
    def videos_destination(self, value: str):
        self.update({'videos_destination': value})

    @property
    def archive_destination(self) -> str:
        return self._config['archive_destination']

    @archive_destination.setter
    def archive_destination(self, value: str):
        self.update({'archive_destination': value})

    @property
    def map_destination(self) -> str:
        return self._config['map_destination']

    @map_destination.setter
    def map_destination(self, value: str):
        self.update({'map_destination': value})

    @property
    def zims_destination(self) -> str:
        return self._config['zims_destination']

    @zims_destination.setter
    def zims_destination(self, value: str):
        self.update({'zims_destination': value})

    @property
    def nav_color(self) -> str:
        return self._config['nav_color']

    @nav_color.setter
    def nav_color(self, value: str):
        self.update({'nav_color': value})


WROLPI_CONFIG: WROLPiConfig = WROLPiConfig()
TEST_WROLPI_CONFIG: WROLPiConfig = None


def get_wrolpi_config() -> WROLPiConfig:
    """Read the global WROLPi yaml config file."""
    global TEST_WROLPI_CONFIG
    if isinstance(TEST_WROLPI_CONFIG, WROLPiConfig):
        return TEST_WROLPI_CONFIG

    global WROLPI_CONFIG
    return WROLPI_CONFIG


def set_test_config(enable: bool):
    global TEST_WROLPI_CONFIG
    TEST_WROLPI_CONFIG = WROLPiConfig() if enable else None


def wrol_mode_enabled() -> bool:
    """Return True if WROL Mode is enabled."""
    return get_wrolpi_config().wrol_mode


def wrol_mode_check(func):
    """Wraps a function so that it cannot be called when WROL Mode is enabled."""

    @wraps(func)
    def check(*a, **kw):
        if wrol_mode_enabled():
            raise WROLModeEnabled()

        # WROL Mode is not enabled, run the function as normal.
        result = func(*a, **kw)
        return result

    return check


def enable_wrol_mode():
    """
    Modify config to enable WROL Mode.

    Stop downloads and Download Manager.
    """
    logger_.warning('ENABLING WROL MODE')
    get_wrolpi_config().wrol_mode = True
    from wrolpi.downloader import download_manager
    download_manager.stop()


async def disable_wrol_mode():
    """
    Modify config to disable WROL Mode.

    Start downloads and Download Manager.
    """
    logger_.warning('DISABLING WROL MODE')
    get_wrolpi_config().wrol_mode = False
    from wrolpi.downloader import download_manager
    await download_manager.enable()


def insert_parameter(func: Callable, parameter_name: str, item, args: Tuple, kwargs: Dict) -> Tuple[Tuple, Dict]:
    """Insert a parameter wherever it fits in the Callable's signature."""
    sig = inspect.signature(func)
    if parameter_name not in sig.parameters:
        raise TypeError(f'Function {func} MUST have a {parameter_name} parameter!')

    args = list(args)

    index = list(sig.parameters).index(parameter_name)
    args.insert(index, item)
    args = tuple(args)

    return args, kwargs


def iterify(kind: type = list):
    """Convenience function to convert the output of the wrapped function to the type provided."""

    def wrapper(func):
        @wraps(func)
        def wrapped(*a, **kw):
            result = func(*a, **kw)
            return kind(result)

        return wrapped

    return wrapper


dt_or_d = Union[datetime, date]


def date_range(start: dt_or_d, end: dt_or_d, steps: int) -> List[dt_or_d]:
    delta = (end - start) // steps
    return [start + (delta * i) for i in range(steps)]


WHITESPACE = re.compile(r'\s')


def remove_whitespace(s: str) -> str:
    return WHITESPACE.sub('', s)


RUN_AFTER = False


def run_after(after: callable, *args, **kwargs) -> callable:
    """Run the `after` function sometime in the future ofter the wrapped function returns."""
    if not inspect.iscoroutinefunction(after):
        synchronous_after = after

        async def after(*a, **kw):
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f'run_after synchronous_after called for {after}')
            return synchronous_after(*a, **kw)

    def wrapper(func: callable):
        if PYTEST and RUN_AFTER is False:
            return func

        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def wrapped(*a, **kw):
                results = await func(*a, **kw)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f'run_after async called for {func}')
                coro = after(*args, **kwargs)
                asyncio.ensure_future(coro)
                return results
        else:
            @wraps(func)
            def wrapped(*a, **kw):
                results = func(*a, **kw)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f'run_after sync called for {func}')
                coro = after(*args, **kwargs)
                asyncio.ensure_future(coro)
                return results

        return wrapped

    return wrapper


MEDIA_DIRECTORY_PERMISSIONS = 0o40755


def check_media_directory():
    """
    Check that the media directory exists and has the correct permissions.  Log an error if the directory
    is unusable.
    """
    result = True
    media_directory = get_media_directory()
    if not media_directory.is_dir():
        logger_.error(f'Media directory does not exist: {media_directory}')
        return False

    permissions = media_directory.stat().st_mode
    if permissions != MEDIA_DIRECTORY_PERMISSIONS:
        logger_.error(f'Media directory has the wrong permissions: {oct(permissions)}')
        result = False

    if not media_directory.is_mount():
        logger_.warning('Media directory is not a mount.')

    try:
        # Write a file into the media directory, log an error if this is not possible.  This file should be cleaned up
        # by tempfile.
        with tempfile.NamedTemporaryFile(dir=media_directory) as tf:
            tf.write(b'test')
    except Exception as e:
        logger_.error(f'Could not write to media directory: {media_directory}', exc_info=e)
        result = False

    return result


def get_absolute_media_path(path: str | Path) -> Path:
    """
    Get the absolute path of file/directory within the config media directory.

    >>> get_media_directory()
    Path('/media')
    >>> get_absolute_media_path('videos/blender')
    Path('/media/videos/blender')

    :raises UnknownDirectory: the directory/path doesn't exist
    """
    if not path:
        raise ValueError('Path cannot be empty!')
    path = get_media_directory() / path
    return path


def get_relative_to_media_directory(path: Union[str, Path]) -> Path:
    """
    Get the path for a file/directory relative to the config media directory.

    >>> get_media_directory()
    Path('/media')
    >>> get_relative_to_media_directory('/media/videos/blender')
    Path('videos/blender')

    :raises UnknownDirectory: the directory/path doesn't exist
    """
    absolute = get_absolute_media_path(path)
    return absolute.relative_to(get_media_directory())


def get_paths_in_parent_directory(paths: List[Union[str, Path]], parent_directory: pathlib.Path) -> List[Path]:
    """Return only those of the provided paths that are children of the provided parent directory."""
    paths = [i if isinstance(i, Path) else Path(i) for i in paths]
    parent_directory = parent_directory.resolve()
    new_paths = []
    for path in paths:
        if parent_directory in path.resolve().parents and path != parent_directory:
            new_paths.append(path)
    return new_paths


def get_paths_in_media_directory(paths: List[Union[str, Path]]) -> List[Path]:
    """Return only those of the provided paths that are children of the media directory."""
    return get_paths_in_parent_directory(paths, get_media_directory())


def minimize_dict(d: dict, keys: Iterable) -> Optional[dict]:
    """Return a new dictionary that contains only the keys provided."""
    if d is None:
        return
    return {k: d[k] for k in set(keys) & d.keys()}


def make_media_directory(path: Union[str, Path]):
    """Make a directory relative within the media directory."""
    media_dir = get_media_directory()
    path = media_dir / str(path)
    path.mkdir(parents=True)


def extract_domain(url: str) -> str:
    """
    Extract the domain from a URL.  Remove leading www.

    >>> extract_domain('https://www.example.com/foo')
    'example.com'
    """
    parsed = urlparse(url)
    domain = parsed.netloc
    if not domain:
        raise ValueError(f'URL does not have a domain: {url=}')
    domain = domain.decode() if hasattr(domain, 'decode') else domain
    if domain.startswith('www.'):
        # Remove leading www.
        domain = domain[4:]
    return domain


def api_param_limiter(maximum: int, default: int = 20) -> callable:
    """Create a function which restricts the maximum number that can be returned.
    Useful for restricting API limit params.

    >>> limiter = api_param_limiter(100)
    >>> limiter(0)
    0
    >>> limiter(100)
    100
    >>> limiter(150)
    100
    """

    def limiter_(i: int) -> int:
        if not i:
            # Limit is not valid, use the default.
            return default
        return min(int(i), maximum)

    return limiter_


def partition(pred, iterable):
    """Use a predicate to partition entries into false entries and true entries

    >>> is_even = lambda i: not i % 2
    >>> partition(is_even, range(10))
    ([0, 2, 4, 6, 8], [1, 3, 5, 7, 9])
    """
    t1, t2 = tee(iterable)
    return list(filter(pred, t2)), list(filterfalse(pred, t1))


@contextlib.contextmanager
def chdir(directory: Union[pathlib.Path, str, None] = None, with_home: bool = False):
    """
    Change the Python working directory in this context.  If no directory is passed, a TemporaryDirectory will be used.

    This also changes the $HOME environment variable to match.
    """
    home_exists = 'HOME' in os.environ
    original_home = os.environ.get('HOME')
    cwd = os.getcwd()
    if directory is None:
        with tempfile.TemporaryDirectory() as d:
            d = os.path.realpath(d)
            try:
                os.chdir(d)
                if with_home:
                    os.environ['HOME'] = d
                yield
            finally:
                os.chdir(cwd)
                if home_exists:
                    os.environ['HOME'] = original_home
                else:
                    del os.environ['HOME']
            return

    try:
        os.chdir(directory)
        if with_home:
            os.environ['HOME'] = str(directory)
        yield
    finally:
        os.chdir(cwd)
        if home_exists:
            os.environ['HOME'] = original_home
        else:
            del os.environ['HOME']
    return


ZIG_TYPE = Union[int, float, complex, Decimal, datetime]


def zig_zag(low: ZIG_TYPE, high: ZIG_TYPE) -> Generator[ZIG_TYPE, None, None]:
    """
    Generate numbers between `low` and `high` that are
    spread out evenly.  Produces infinite results.

    >>> list(zig_zag(0, 10))
    [0, 5, 2, 7, 1, 3, 6, 8, 0, 1, 3, 4, 5, 6, 8, 9]
    >>> list(zig_zag(0, 5))
    [0, 2, 1, 3, 0, 1, 3, 4]
    >>> list(zig_zag(50.0, 100.0))
    [50.0, 75.0, 62.5, 87.5, 56.25, 68.75, 81.25, 93.75, 53.125, 59.375, 65.625]
    """
    output_type = type(low)
    if not isinstance(high, type(low)):
        raise ValueError(f'high and low must be same type')
    if isinstance(low, datetime) and isinstance(high, datetime):
        low, high = low.timestamp(), high.timestamp()
        output_type = from_timestamp

    # Special thanks to my wife for helping me solve this! :*
    results = set()
    num = low
    divisor = 2
    diff = high - low
    while True:
        if num not in results:
            yield output_type(num)
            results.add(num)
        num += diff / divisor
        if num >= high:
            divisor *= 2
            num = low + (diff / divisor)


def walk(path: Path) -> Generator[Path, None, None]:
    """Recursively walk a directory structure yielding all files and directories."""
    if not path.is_dir():
        raise ValueError('Can only walk a directory.')

    for path in path.iterdir():
        yield path
        if path.is_dir():
            yield from walk(path)


def get_files_and_directories(directory: Path):
    """Walk a directory, return a tuple of all files and all directories within.  (Not recursive)."""
    if not directory.exists():
        raise FileNotFoundError(f'Directory does not exist: {directory}')
    if not directory.is_dir():
        raise ValueError('Can only walk a directory.')

    directories, files = partition(lambda i: i.is_dir(), directory.iterdir())
    return files, directories


# These characters are invalid in Windows or Linux.
INVALID_FILE_CHARS = re.compile(r'[/<>:|"\\?*%!\n\r]')

SPACE_FILE_CHARS = re.compile(r'(  +)|(\t+)')


def escape_file_name(name: str) -> str:
    """Remove any invalid characters in a file name."""
    # Replace forward-slash (linux directories) with unicode Big Solidus (U+29F8)
    name = name.replace('/', '⧸')
    # Replace commonly used pipe with dash.
    name = name.replace(' | ', ' - ')
    # Replace multiple spaces or tabs with a single space.
    name = SPACE_FILE_CHARS.sub(' ', name)
    name = INVALID_FILE_CHARS.sub('', name)
    return name.strip()


# Maximum length is probably 255, but we need more length for large suffixes like `.readability.json`, and temporary
# downloading suffixes from yt-dlp.
MAXIMUM_FILE_LENGTH = 140


def trim_file_name(path: str | pathlib.Path) -> str | pathlib.Path:
    """Shorten the file name only if it is longer than the file system supports.  Trim from the end of the name until
     the name is short enough (preserving any suffix)."""
    name_type = pathlib.Path if isinstance(path, pathlib.Path) else str
    parent = path.parent if isinstance(path, pathlib.Path) else '/'.join(i for i in path.split('/')[:-1])
    path = path.name if isinstance(path, pathlib.Path) else path

    if len(path) < MAXIMUM_FILE_LENGTH:
        return name_type(path)

    # Don't trim the filename to exactly 256 characters.
    # This is because a FileGroup will have varying filename lengths.
    from wrolpi.files.lib import split_path_stem_and_suffix
    stem, suffix = split_path_stem_and_suffix(path)
    excess = MAXIMUM_FILE_LENGTH - len(suffix)
    new_name = stem[:excess].strip() + suffix
    if parent:
        if name_type == pathlib.Path:
            return parent / new_name
        return f'{parent}/{new_name}'
    return name_type(new_name)


def native_only(func: callable):
    """Wraps a function.  Raises NativeOnly if run while Dockerized."""

    @wraps(func)
    def wrapped(*a, **kw):
        if DOCKERIZED:
            raise NativeOnly('Only supported on a Raspberry Pi')
        return func(*a, **kw)

    return wrapped


def recursive_map(obj: Any, func: callable):
    """
    Apply `func` to all values of any dictionaries; or items in any list/set/tuple.

    >>> recursive_map({'foo ': ' bar '}, lambda i: i.strip() if hasattr(i, 'strip') else i)
    {'foo ': 'bar'}
    >>> recursive_map(['foo ', ' bar '], lambda i: i.strip() if hasattr(i, 'strip') else i)
    ['foo', 'bar']
    """
    if isinstance(obj, dict):
        obj = obj.copy()
        for key, value in obj.items():
            obj[key] = recursive_map(value, func)
        return obj
    elif isinstance(obj, (list, set, tuple)):
        type_ = type(obj)
        return type_(map(lambda i: recursive_map(i, func), obj))
    return func(obj)


@contextlib.asynccontextmanager
async def aiohttp_session(timeout: int = None) -> ClientSession:
    """Convenience function because aiohttp timeout cannot be None."""
    if timeout:
        timeout = aiohttp.ClientTimeout(total=timeout) if timeout else None
        async with aiohttp.ClientSession(timeout=timeout) as session:
            yield session
    else:
        async with aiohttp.ClientSession() as session:
            yield session


@contextlib.asynccontextmanager
async def aiohttp_post(url: str, json_, timeout: int = None, headers: dict = None) -> ClientResponse:
    """Perform an async aiohttp POST request.  Yield the response in a session."""
    headers = headers or DEFAULT_HTTP_HEADERS
    async with aiohttp_session(timeout) as session:
        async with session.post(url, json=json_, headers=headers) as response:
            yield response


@contextlib.asynccontextmanager
async def aiohttp_get(url: str, timeout: int = None, headers: dict = None) -> ClientResponse:
    """Perform an async aiohttp GET request.  Yield the response in a session."""
    headers = headers or DEFAULT_HTTP_HEADERS
    async with aiohttp_session(timeout) as session:
        async with session.get(url, headers=headers) as response:
            yield response


@contextlib.asynccontextmanager
async def aiohttp_head(url: str, timeout: int = None, headers: dict = None) -> ClientResponse:
    """Perform an async aiohttp HEAD request.  Yield the response in a session."""
    headers = headers or DEFAULT_HTTP_HEADERS
    async with aiohttp_session(timeout) as session:
        async with session.head(url, headers=headers) as response:
            yield response


@dataclass
class DownloadFileInfo:
    """Information about a file that can be downloaded."""
    name: str = None
    size: int = None
    type: str = None
    accept_ranges: str = None
    status: int = None
    location: str = None


FILENAME_MATCHER = re.compile(r'.*filename="(.*)"')


async def get_download_info(url: str, timeout: int = 60) -> DownloadFileInfo:
    """Gets information (name, size, etc.) about a downloadable file at the provided URL."""
    async with aiohttp_head(url, timeout) as response:
        download_logger.debug(f'{response.headers=}')

        info = DownloadFileInfo(
            type=response.headers.get('Content-Type'),
            size=int(response.headers['Content-Length']) if 'Content-Length' in response.headers else None,
            accept_ranges=response.headers.get('Accept-Ranges'),
            status=response.status,
            location=response.headers.get('Location'),
        )

        disposition = response.headers.get('Content-Disposition')

    if disposition and 'filename' in disposition:
        if (match := FILENAME_MATCHER.match(disposition)) and (groups := match.groups()):
            info.name = groups[0]
    else:
        # No Content-Disposition with filename, use the Location or URL name.
        if info.location:
            parsed = urlparse(info.location)
        else:
            parsed = urlparse(url)
        info.name = parsed.path.split('/')[-1]

    return info


download_logger = logger.getChild('download')


def human_bandwidth(bps: int) -> str:
    """Convert bits per second to a more readable format.

    >>> human_bandwidth(2000)
    # '2 Kbps'
    """
    units = ['bps', 'Kbps', 'Mbps', 'Gbps', 'Tbps']
    unit = 0
    while bps > 1000 and unit <= len(units):
        bps /= 1000
        unit += 1

    return f'{int(bps)} {units[unit]}'


modelers = []


def register_modeler(modeler: callable):
    modelers.append(modeler)
    return modeler


async def apply_modelers():
    for modeler in modelers:
        logger_.info(f'Applying modeler {modeler.__name__}')
        try:
            await modeler()
        except Exception as e:
            logger_.error(f'Modeler {modeler.__name__} raised error', exc_info=e)
            if PYTEST:
                raise
        # Sleep to catch cancel.
        await asyncio.sleep(0)


REFRESH_CLEANUP = []


def register_refresh_cleanup(func: callable):
    REFRESH_CLEANUP.append(func)
    return func


async def apply_refresh_cleanup():
    # TODO convert all functions to async so refresh functions can be used.
    for func in REFRESH_CLEANUP:
        slow_message = f'After refresh cleanup {func.__name__} took %(elapsed)s seconds'
        with slow_logger(5, slow_message, logger__=logger_):
            try:
                logger_.info(f'Applying refresh cleanup {func.__name__}')
                func()
            except Exception as e:
                logger_.error(f'Refresh cleanup {func.__name__} failed!', exc_info=e)
                if PYTEST:
                    raise
        # Sleep to catch cancel.
        await asyncio.sleep(0)


def chunks(it: Iterable, size: int):
    """Split an iterable into iterables of the defined length."""
    it = iter(it)
    return iter(lambda: tuple(islice(it, size)), ())


def chunks_by_stem(it: List[Union[pathlib.Path, str, int]], size: int) -> Generator[List[pathlib.Path], None, None]:
    """
    Attempt to split a list of paths near the defined size.  Keep groups of files together when they share
    matching names.

    >>> files = ['1.mp4', '1.txt', '2.mp4', '2.txt', '2.png', '3.mp4']
    >>> chunks_by_stem(files, 2)
    [['1.mp4', '1.txt'], ['2.mp4', '2.txt', '2.png'], ['3.mp4']]
    >>> chunks_by_stem(files, 3)
    [['1.mp4', '1.txt', '2.mp4', '2.txt', '2.png'], ['3.mp4']]
    """
    if not isinstance(size, int) or size < 1:
        raise ValueError('size must be a positive integer')

    if not it or len(it) < size:
        yield sorted(it)
        return

    if not isinstance(it, list):
        raise ValueError('iterable must a list')

    from wrolpi.files.lib import split_path_stem_and_suffix
    it = sorted(it.copy())
    index = size
    last_stem = None
    while it:
        if index >= len(it):
            # Ran out of items, yield what is left.
            yield it
            return
        path = it[index]
        stem, _ = split_path_stem_and_suffix(path)
        if last_stem and stem != last_stem:
            # Found a break in the path names, yield and reset.
            chunk, it = it[:index], it[index:]
            index = size
            last_stem = None
            yield chunk
            continue
        # Didn't find a name change, try again.
        last_stem = stem
        index += 1


@contextlib.contextmanager
def timer(name, level: str = 'debug', logger__: logging.Logger = None):
    """Prints out the time elapsed during the call of some block.

    Example:
        with timer('sleepy'):
            time.sleep(10)

    """
    level = level.lower()
    logger__ = logger__ or logger_
    before = datetime.now()
    try:
        yield
    finally:
        elapsed = (datetime.now() - before).total_seconds()
        msg = f'{name} elapsed {elapsed} seconds'
        getattr(logger__, level)(msg)


@contextlib.contextmanager
def slow_logger(max_seconds: int, message: str, logger__=logger_, level=logging.WARNING):
    """Only logs when the context duration exceeds the `max_seconds`."""
    before = now()
    try:
        yield
    finally:
        elapsed = (now() - before).total_seconds()
        if elapsed >= max_seconds:
            logger__.log(level, message % dict(elapsed=elapsed))


TIMERS = dict()


@contextlib.contextmanager
def cum_timer(name: str):
    """Track time usage within this context's name.  The cumulative calls to this context will be printed on exit."""
    before = now()
    try:
        yield
    finally:
        total_seconds = (now() - before).total_seconds()
        existing_seconds, calls = TIMERS.get(name, (0, 0))
        TIMERS[name] = (existing_seconds + total_seconds, calls + 1)


@atexit.register
def print_timer():
    """Print any cumulative timers that have been stored during exit."""
    if not TIMERS:
        return

    total = sum(i[0] for i in TIMERS.values())
    for name, (seconds, calls) in sorted(TIMERS.items(), key=lambda i: i[1]):
        percent = int((seconds / total) * 100)
        seconds = round(seconds, 5)
        print(f'CUM_TIMER: {repr(name)} elapsed {seconds} cumulative seconds ({percent}%)'
              f' {calls} calls', file=sys.stderr)


def limit_concurrent(limit: int, throw: bool = False):
    """Wrapper that limits the amount of concurrently running functions."""
    sema = multiprocessing.Semaphore(value=limit)

    def wrapper(func: callable):
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def wrapped(*a, **kw):
                acquired = sema.acquire(block=False)
                if not acquired:
                    if throw:
                        raise ValueError(f'Reached concurrent limit! {func=}')
                    return
                try:
                    return await func(*a, **kw)
                finally:
                    sema.release()

            return wrapped
        else:
            @wraps(func)
            def wrapped(*a, **kw):
                acquired = sema.acquire(block=False)
                if not acquired:
                    if throw:
                        raise ValueError(f'Reached concurrent limit! {func=}')
                    return
                try:
                    return func(*a, **kw)
                finally:
                    sema.release()

            return wrapped

    return wrapper


def truncate_object_bytes(obj: Union[List[str], str, None, Generator], maximum_bytes: int) -> Union[List[str], str]:
    """
    Shorten an object.  This is useful when inserting something into a tsvector.

    >>> i = ['foo',  'foo',  'foo',  'foo',  'foo', 'foo',  'foo',  'foo',  'foo',  'foo']
    >>> truncate_object_bytes(i, 100)
    ['foo',  'foo',  'foo',  'foo',  'foo']
    """
    if not obj:
        # Can't decrease an empty object.
        return obj
    size = sys.getsizeof(obj)
    if size < maximum_bytes:
        return obj
    index = -1 * round(len(obj) * .2)
    obj = obj[:index or -1]
    return truncate_object_bytes(obj, maximum_bytes)


def truncate_generator_bytes(gen: Generator, maximum_bytes: int) -> Generator:
    """Yield from a generator until the chunk sizes go over the maximum_bytes."""
    total_size = 0
    while total_size < maximum_bytes:
        try:
            chunk = next(gen)
            total_size += sys.getsizeof(chunk)
            yield chunk
        except StopIteration:
            return


BACKGROUND_TASKS = set()


def add_background_task(task: Task):
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)


def background_task(coro) -> Task:
    """Convenience function which creates an asyncio task for the provided coroutine.

    The task is stored in a global set of background tasks so the task will not be discarded by the garbage collector.
    """

    async def error_logger():
        try:
            await coro
        except Exception as e:
            logger_.error('Background task had error:', exc_info=e)

    task = asyncio.create_task(error_logger())
    add_background_task(task)
    return task


async def cancel_background_tasks():
    """Cancels any background async tasks, if any."""
    if BACKGROUND_TASKS:
        logger_.warning(f'Canceling {len(BACKGROUND_TASKS)} background tasks')
        for task in BACKGROUND_TASKS:
            task.cancel()
            await asyncio.gather(*BACKGROUND_TASKS)


async def await_background_tasks():
    """Awaits all background tasks, used only for testing."""
    if not PYTEST:
        raise RuntimeError('await_background_tasks should only be used for testing')

    for background_task in BACKGROUND_TASKS.copy():
        await background_task


def get_warn_once(message: str, logger__: logging.Logger, level=logging.ERROR):
    """Create a function that will report an error only once.

    This is used when a function will be called many times, but the error is not important."""

    def warn_once(exception: Exception):
        if PYTEST:
            # No need to fill pytest logs with these warnings.
            return

        from wrolpi.api_utils import api_app
        if not api_app.shared_ctx.warn_once.get(message):
            logger__.log(level, message, exc_info=exception)
            api_app.shared_ctx.warn_once.update({message: True})

    return warn_once


def get_global_statistics():
    from wrolpi.db import get_db_curs
    with get_db_curs() as curs:
        curs.execute('select pg_database_size(current_database())')
        db_size = curs.fetchall()[0][0]

    return dict(
        db_size=db_size,
    )


REFRESH_TASKS: List[Task] = []


async def cancel_refresh_tasks():
    """Cancel all refresh tasks, if any."""
    if REFRESH_TASKS:
        logger_.warning(f'Canceling {len(REFRESH_TASKS)} refreshes')
        for task in REFRESH_TASKS:
            task.cancel()
        await asyncio.gather(*REFRESH_TASKS)


def cancelable_wrapper(func: callable):
    """Wraps an async function so that it will be canceled by `cancel_refresh_tasks`."""

    @wraps(func)
    async def wrapped(*args, **kwargs):
        if PYTEST:
            return await func(*args, **kwargs)

        task = background_task(func(*args, **kwargs))
        REFRESH_TASKS.append(task)

    return wrapped


WHITESPACE_SPLITTER = re.compile(r'\s+')
TAB = re.compile(r'\t+')


def split_lines_by_length(text: str, max_line_length: int = 38) -> str:
    """
    Break up any long lines along word boundaries.

    Newlines are preserved, but whitspace (spaces/tabs) is replaced with one space.

    @param max_line_length: The most amount of characters a line will contain.  38 is default for mobile vertical.

    >>> split_lines_by_length('Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do')
    'Lorem ipsum dolor sit amet,\nconsectetur adipiscing elit, sed do'
    """
    if not text:
        return text

    text = TAB.sub(' ', text)
    new_text = ''
    for line in text.splitlines():
        if len(line) > max_line_length:
            # This line is too long, break it up.
            new_line = ''
            words = WHITESPACE_SPLITTER.split(line)
            while words:
                word = words.pop(0)
                if len(possible_line := f'{new_line} {word}') <= max_line_length:
                    new_line = possible_line
                else:
                    # New word makes the line too long, start a new line.
                    new_text += f'\n{new_line.strip()}'
                    new_line = word
            new_text += f'\n{new_line}'
        else:
            new_text += f'\n{line}'
    return new_text.lstrip('\n')


def resolve_generators(obj: Union[Dict, List]) -> Any:
    """Recursively find generators within an object/list, resolve them.

    Returns a new object/list without any generators."""
    if isinstance(obj, str):
        return obj
    elif isinstance(obj, Tuple):
        return tuple(resolve_generators(i) for i in obj)
    elif isinstance(obj, Set):
        return {resolve_generators(i) for i in obj}
    elif isinstance(obj, Dict):
        return {resolve_generators(i): resolve_generators(j) for i, j in obj.items()}
    elif isinstance(obj, range):
        return list(obj)
    elif isinstance(obj, GeneratorType) or isinstance(obj, Iterable):
        return [resolve_generators(i) for i in obj]
    return obj


def url_strip_host(url: str) -> str:
    """Return a relative URL without the host or scheme.

    >>> url_strip_host('https://example.com/foo')
    '/foo'
    """
    url = urlparse(url)
    url = urlunsplit(('', '', url.path, url.query, url.fragment))
    return url or '/'


def get_html_soup(html: Union[bytes, str]) -> bs4.BeautifulSoup:
    soup = BeautifulSoup(html, features='html.parser')
    return soup


def extract_html_text(html: str) -> str:
    soup = get_html_soup(html)

    # kill all script and style elements
    for script in soup(["script", "style"]):
        script.extract()  # rip it out

    text = soup.body.get_text()

    # break into lines and remove leading and trailing space on each
    lines = (line.strip() for line in text.splitlines())
    # break multi-headlines into a line each
    chunks_ = (phrase.strip() for line in lines for phrase in line.split("  "))
    # drop blank lines
    text = '\n'.join(chunk for chunk in chunks_ if chunk)

    return text


def extract_headlines(entries: List[str], search_str: str) -> List[Tuple[str, float]]:
    """Use Postgres to extract Headlines and ranks of the `search_str` from the provided entries."""
    from wrolpi.db import get_db_curs

    source = json.dumps([{'content': i} for i in entries])
    with get_db_curs() as curs:
        stmt = '''
               WITH vectored AS (
                   -- Convert the "source" json to a recordset.
                   with source as (select * from json_to_recordset(%s::json) AS (content TEXT))
                   select to_tsvector('english'::regconfig, source.content) AS vector,
                          source.content
                   from source)
               SELECT ts_headline(vectored.content, websearch_to_tsquery(%s),
                                  'MaxFragments=10, MaxWords=8, MinWords=7'),
                      ts_rank(vectored.vector, websearch_to_tsquery(%s))
               FROM vectored \
               '''
        curs.execute(stmt, [source, search_str, search_str])
        headlines = [tuple(i) for i in curs.fetchall()]

    return headlines


async def search_other_estimates(tag_names: List[str]) -> dict:
    """Estimate other things that are Tagged."""
    from wrolpi.db import get_db_curs

    if not tag_names:
        return dict(
            channel_count=0,
        )

    with get_db_curs() as curs:
        stmt = '''
               SELECT COUNT(c.id)
               FROM channel c
                        LEFT OUTER JOIN public.tag t on t.id = c.tag_id
               WHERE t.name = %(tag_name)s \
               '''
        # TODO handle multiple tags
        params = dict(tag_name=tag_names[0])
        curs.execute(stmt, params)

        channel_count = curs.fetchone()[0]

    others = dict(
        channel_count=channel_count,
    )
    return others


def replace_file(file: pathlib.Path | str, contents: str | bytes, missing_ok: bool = False):
    """Rename `file` to a temporary path, write contents to `file`, then, delete temporary file only if successful.
    The original file will be restored if any of these steps fail."""
    file = pathlib.Path(file)

    if missing_ok is False and not file.is_file():
        raise FileNotFoundError(f'Cannot replace non-existent file: {str(file)}')

    temporary_path = pathlib.Path(str(file) + '.tmp')
    if temporary_path.exists():
        raise RuntimeError(f'Cannot replace file, temporary path already exists!  {str(temporary_path)}')

    if not contents:
        raise RuntimeError('Refusing to replace file with empty contents')

    try:
        if file.exists():
            file.rename(temporary_path)
        mode = 'wb' if isinstance(contents, bytes) else 'wt'
        with file.open(mode) as fp:
            fp.write(contents)
            os.fsync(fp.fileno())
        if file.exists() and temporary_path.exists():
            # New contents have been written, delete the old file.
            temporary_path.unlink()
    except Exception as e:
        logger.error(f'Failed to replace file: {str(file)}', exc_info=e)
        if temporary_path.exists():
            # Move original file back.
            if file.exists():
                file.unlink()
            temporary_path.rename(file)
        elif file.exists():
            logger.error(f'Replacing file, but original file still exists: {str(file)}')
        else:
            logger.critical('Neither original, nor temporary file exist.  I am so sorry.')
        raise
    finally:
        if file.is_file() and file.stat().st_size > 0 and temporary_path.is_file():
            temporary_path.unlink()


def format_json_file(file: pathlib.Path, indent: int = 2):
    """Reformat the contents of a JSON file to include indentation to increase readability."""
    if not indent or indent <= 0:
        raise RuntimeError('Ident must be greater than 0')
    if not file or not file.is_file():
        raise RuntimeError(f'File does not exist: {file}')

    content = json.loads(file.read_text())
    content = json.dumps(content, indent=indent, sort_keys=True)
    replace_file(file, content)


def format_html_string(html: str | bytes) -> str:
    if not html.strip():
        raise RuntimeError('Refusing to format empty HTMl string.')

    soup = BeautifulSoup(html, features='lxml')
    return soup.prettify()


def format_html_file(file: pathlib.Path):
    """Reformat the contents of an HTML file to include indentation to increase readability."""
    if not file or not file.is_file():
        raise RuntimeError(f'File does not exist: {file}')

    pretty = format_html_string(file.read_text())
    replace_file(file, pretty)


def html_screenshot(html: bytes | str) -> bytes:
    """Return a PNG screenshot of the provided HTML."""
    # Set Chromium to headless.  Use a wide window size so that screenshot will be the "desktop" version of the page.
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    options.add_argument('disable-gpu')
    options.add_argument('window-size=1280x720')

    with tempfile.NamedTemporaryFile('wb', suffix='.html') as fh:
        fh.write(html.encode() if isinstance(html, str) else html)
        fh.flush()

        with webdriver.Chrome(chrome_options=options) as driver:
            driver.get(f'file://{fh.name}')
            driver.set_window_size(1280, 720)
            screenshot = driver.get_screenshot_as_png()
            return screenshot


def chain(iterable: Union[List, Tuple], length: int) -> List:
    """
    Steps through the provided list and generates slices of the provided length.

    >>> list(chain([1, 2, 3, 4], 2))
    [[1, 2], [2, 3], [3, 4]]

    >>> list(chain([1, 2, 3, 4], 3))
    [[1, 2, 3], [2, 3, 4]]
    """
    if not iterable:
        return

    position = 0
    maximum = 1 + len(iterable) - length
    yielded = False
    while position < maximum:
        tick = iterable[position:position + length]
        yield tick
        yielded = True
        position += 1
    if not yielded:
        # Not enough items to iterate.  Yield the original iterable.
        yield iterable


def get_title_from_html(html: str, url: str = None) -> str:
    """
    Try and get the title from the
    """
    soup = get_html_soup(html)
    try:
        return soup.title.string.strip()
    except Exception:  # noqa
        logger_.debug(f'Unable to extract title {url}')


@wrol_mode_check
def can_connect_to_server(hostname: str, port: int = 80) -> bool:
    """Return True only if `hostname` responds."""
    # Thanks https://stackoverflow.com/questions/20913411/test-if-an-internet-connection-is-present-in-python
    try:
        # connect to the host -- tells us if the host is actually
        # reachable
        conn = socket.create_connection((hostname, port))
        conn.close()
        return True
    except Exception as e:
        logger_.debug('can_connect_to_server encountered error', exc_info=e)
    return False


def is_valid_hex_color(hex_color: str) -> bool:
    # Regular expression to match valid HTML hex color codes
    hex_color_regex = re.compile(r'^#([A-F0-9]{6}|[A-F0-9]{3})$', re.IGNORECASE)
    return bool(hex_color_regex.match(hex_color))


def is_hardlinked(path: pathlib.Path) -> bool:
    """Returns True only if `path` has more than one link."""
    return path.stat().st_nlink > 1


def unique_by_predicate(
        iterable: list | tuple | set | Generator,
        predicate: callable = None,
) -> list | tuple | set:
    """Finds the first unique items in the provided iterable based on the predicate function.  Order is preserved.

    `predicate` defaults to the items themselves.

    >>> unique_by_predicate([['apple', 'banana', 'pear', 'kiwi', 'plum', 'peach']], lambda i: len(i))
    # [ 'apple', 'banana', 'pear' ]
    >>> unique_by_predicate([Path('foo.txt'), Path('foo.mp4'), Path('bar.txt')], lambda i: i.stem)
    # [ Path('foo.txt'), Path('bar.txt') ]
    >>> unique_by_predicate([1, 1, 2, 3, 3, 3, 3, 4], None)
    # [ 1, 2, 3, 4 ]
    """
    predicate = predicate or (lambda i: i)  # Return an iterable based off the object itself by default.
    seen = set()
    unique_items = [i for i in iterable if not ((key := predicate(i)) in seen or seen.add(key))]
    if isinstance(iterable, Generator):
        # Return a list when provided iterable is a Generator.
        return unique_items
    # Return the same type as the provided iterable
    return iterable.__class__(unique_items)


def cached_multiprocessing_result(func: callable):
    """Simple multiprocessing results cacher which uses the args/kwargs of the wrapped function as the caching key.

    @warning: Asumes the wrapped function is async.
    """

    @functools.wraps(func)
    async def wrapped(*args, **kwargs):
        from wrolpi.api_utils import api_app
        key = (func.__name__, *args, *tuple(kwargs.items()))
        if result := api_app.shared_ctx.cache.get(key):
            return result

        result = await func(*args, **kwargs)
        api_app.shared_ctx.cache[key] = result
        return result

    return wrapped


def create_empty_config_files() -> list[str]:
    """Creates config files only if they do not exist and will not conflict with the DB."""
    from modules.inventory.common import get_inventories_config
    from modules.videos.lib import get_channels_config, get_videos_downloader_config
    from wrolpi.downloader import get_download_manager_config
    from wrolpi.tags import get_tags_config
    from wrolpi.db import get_db_session

    created = []  # The names of the configs that are created.

    if not get_wrolpi_config().get_file().is_file():
        get_wrolpi_config().save(overwrite=True)
        created.append(get_wrolpi_config().get_file().name)

    with get_db_session() as session:
        if not get_channels_config().get_file().is_file():
            from modules.videos.models import Channel
            if session.query(Channel).count() == 0:
                # No Channels will be deleted, create the empty Channels config file.
                get_channels_config().save(overwrite=True)
                created.append(get_channels_config().get_file().name)

        if not get_tags_config().get_file().is_file():
            from wrolpi.tags import Tag
            if session.query(Tag).count() == 0:
                # No Tags will be deleted, create the empty Tags config file.
                get_tags_config().save(overwrite=True)
                created.append(get_tags_config().get_file().name)

        if not get_download_manager_config().get_file().is_file():
            from wrolpi.downloader import Download
            if session.query(Download).count() == 0:
                # No Downloads will be deleted, create the empty Download Manager config file.
                get_download_manager_config().save(overwrite=True)
                created.append(get_download_manager_config().get_file().name)

        if not get_videos_downloader_config().get_file().is_file():
            get_videos_downloader_config().save(overwrite=True)
            created.append(get_videos_downloader_config().get_file().name)

        if not get_inventories_config().get_file().is_file():
            from modules.inventory.models import Inventory
            if session.query(Inventory).count() == 0:
                # No Inventories will be deleted, create the empty Inventory config file.
                get_inventories_config().save(overwrite=True)
                created.append(get_inventories_config().get_file().name)

    return created
