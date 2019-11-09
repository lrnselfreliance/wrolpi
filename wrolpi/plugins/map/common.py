from pathlib import Path

import yaml

MY_DIR: Path = Path(__file__).parent
CONFIG_PATH = MY_DIR / 'local.yaml'


def get_config():
    if not CONFIG_PATH.exists():
        return None

    with open(str(CONFIG_PATH), 'rt') as fh:
        config = yaml.load(fh, Loader=yaml.Loader)
    return config


def save_config(settings: dict):
    with open(str(CONFIG_PATH), 'wt') as fh:
        yaml.dump(settings, fh)
