from wrolpi.common import env, create_pagination_dict
from wrolpi.tools import get_db_context


def search(search_str, offset, limit: int = 20):
    result = {}
    with get_db_context() as (db_conn, db):
        curs = db_conn.cursor()
        query = 'SELECT id, ts_rank_cd(textsearch, to_tsquery(%s)) FROM video WHERE ' \
                'textsearch @@ to_tsquery(%s) ORDER BY 2 OFFSET %s LIMIT %s'
        curs.execute(query, (search_str, search_str, offset, limit))
        results = list(curs.fetchall())

        if len(results) == 21:
            more = True
        else:
            more = False
        results = results[:20]

        videos = []
        Video = db['video']
        if results:
            videos = [dict(i) for i in Video.get_where(Video['id'].In([i[0] for i in results]))]

        pagination = create_pagination_dict(offset, limit, more)

        video_weights = {i[0]: i[1] for i in results}
        for video in videos:
            video['weight'] = video_weights[video['id']]
        template = env.get_template('wrolpi/plugins/videos/templates/search_video.html')
        result['videos'] = {
            'template': template,
            'items': videos,
            'pagination': pagination,
        }
    return result
