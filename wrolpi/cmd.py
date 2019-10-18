from wrolpi.common import logger
from wrolpi.tools import get_db_context


def update_db_with_conn(plugins, db_conn, db):
    for plugin in plugins.values():
        sql = plugin.get_update_sql(db_conn, db)
        curs = db.get_cursor()
        curs.execute(sql)
    db_conn.commit()


def update_db(plugins):
    with get_db_context() as (db_conn, db):
        update_db_with_conn(plugins, db_conn, db)
    return 0


def import_settings_configs(plugins):
    logger.info('Importing configs')
    for plugin in plugins.values():
        plugin.import_settings_config()


def save_settings_configs(plugins):
    for plugin in plugins.values():
        plugin.save_settings_config()
