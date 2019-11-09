from pathlib import Path

import yaml

MY_DIR: Path = Path(__file__).parent
DOWNLOADS_PATH = MY_DIR / 'local.yaml'

DEFAULT_DOWNLOADS = {
    'pbf_urls': {},
}


def get_downloads():
    if not DOWNLOADS_PATH.exists():
        return DEFAULT_DOWNLOADS

    with open(str(DOWNLOADS_PATH), 'rt') as fh:
        config = yaml.load(fh, Loader=yaml.Loader)
    return config


def save_downloads(settings: dict):
    with open(str(DOWNLOADS_PATH), 'wt') as fh:
        yaml.dump(settings, fh)
