from dictorm import DictDB

from wrolpi.common import env


def video_search(db: DictDB, search_str, offset):
    db_conn = db.conn
    template = env.get_template('wrolpi/plugins/videos/templates/search_video.html')
    curs = db_conn.cursor()
    # Get the total count
    query = 'SELECT COUNT(*) FROM video WHERE textsearch @@ to_tsquery(%s) OFFSET %s'
    curs.execute(query, (search_str, offset))
    total = curs.fetchone()[0]

    # Get the search results
    query = 'SELECT id, ts_rank_cd(textsearch, to_tsquery(%s)) FROM video WHERE ' \
            'textsearch @@ to_tsquery(%s) ORDER BY 2 OFFSET %s'
    curs.execute(query, (search_str, search_str, offset))
    results = list(curs.fetchall())

    videos = []
    Video = db['video']
    if results:
        videos = [dict(i) for i in Video.get_where(Video['id'].In([i[0] for i in results]))]

    results = {
        'template': template,
        'items': videos,
        'total': total,
    }
    return results
