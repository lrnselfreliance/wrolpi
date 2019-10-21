from wrolpi.tools import get_db_context


def search(search_str):
    result = {}
    with get_db_context() as (db_conn, db):
        Video = db['video']
        curs = db_conn.cursor()
        curs.execute('SELECT id, ts_rank_cd(textsearch, to_tsquery(%s)) FROM video WHERE textsearch @@ to_tsquery(%s)',
                     (search_str, search_str))
        results = curs.fetchall()
        video_ids = [i for (i, j) in results]
        videos = Video.get_where(Video['id'].In(video_ids))
        result['videos'] = list(videos)
    return result
