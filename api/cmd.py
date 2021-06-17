from api.common import logger

logger = logger.getChild(__name__)


def import_settings_configs(modules):
    logger.info('Importing configs')
    for module in modules.values():
        module.import_settings_config()
