from wrolpi.common import env
from wrolpi.tools import get_db_context


def search(search_str):
    result = {}
    with get_db_context() as (db_conn, db):
        Video = db['video']
        curs = db_conn.cursor()
        query = 'SELECT id, ts_rank_cd(textsearch, to_tsquery(%s)) FROM video WHERE ' \
                'textsearch @@ to_tsquery(%s) ORDER BY 2'
        curs.execute(query, (search_str, search_str))
        results = curs.fetchall()
        video_weights = {i[0]: i[1] for i in results}
        videos = []
        if results:
            videos = [dict(i) for i in Video.get_where(Video['id'].In([i[0] for i in results]))]
        for video in videos:
            video['weight'] = video_weights[video['id']]
        template = env.get_template('wrolpi/plugins/videos/templates/search_video.html')
        result['videos'] = {
            'template': template,
            'items': videos,
        }
    return result
