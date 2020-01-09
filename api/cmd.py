from api.common import logger


def import_settings_configs(modules):
    logger.info('Importing configs')
    for module in modules.values():
        module.import_settings_config()


def save_settings_configs(modules):
    for module in modules.values():
        module.save_settings_config()
