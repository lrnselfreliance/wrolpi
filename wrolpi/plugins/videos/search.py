from wrolpi.common import env
from wrolpi.tools import get_db_context


def search(search_str, offset, limit):
    result = {}
    with get_db_context() as (db_conn, db):
        template = env.get_template('wrolpi/plugins/videos/templates/search_video.html')
        curs = db_conn.cursor()
        query = 'SELECT id, ts_rank_cd(textsearch, to_tsquery(%s)) FROM video WHERE ' \
                'textsearch @@ to_tsquery(%s) ORDER BY 2 OFFSET %s LIMIT %s'
        curs.execute(query, (search_str, search_str, offset, limit))
        results = list(curs.fetchall())

        videos = []
        Video = db['video']
        if results:
            videos = [dict(i) for i in Video.get_where(Video['id'].In([i[0] for i in results]))]

        result['videos'] = {
            'template': template,
            'items': videos,
        }
    return result
