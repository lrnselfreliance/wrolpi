from wrolpi.common import logger


def import_settings_configs(plugins):
    logger.info('Importing configs')
    for plugin in plugins.values():
        plugin.import_settings_config()


def save_settings_configs(plugins):
    for plugin in plugins.values():
        plugin.save_settings_config()
