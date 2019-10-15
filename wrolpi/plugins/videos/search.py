from wrolpi.common import get_db_context


def search(search_str):
    result = {}
    with get_db_context() as (db_conn, db):
        Video = db['video']
        curs = db_conn.cursor()
        curs.execute('SELECT id FROM video WHERE textsearch @@ to_tsquery(%s)', (search_str,))
        video_ids = [i for (i,) in curs.fetchall()]
        videos = Video.get_where(Video['id'].In(video_ids))
        result['videos'] = list(videos)
    return result
