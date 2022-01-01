from sanic_openapi import doc


class RetrieveURLsRequest:
    limit = doc.Integer()
    offset = doc.Integer()
    domain = doc.String()


class ArchiveDict:
    id = doc.Integer()
    url_id = doc.Integer()
    domain_id = doc.Integer()
    singlefile_path = doc.String()
    readability_path = doc.String()
    readability_json_path = doc.String()
    readability_txt_path = doc.String()
    screenshot_path = doc.String()
    title = doc.String()
    archive_datetime = doc.DateTime()


class DomainDict:
    id = doc.Integer()
    domain = doc.String()


class URLDict:
    id = doc.Integer()
    url = doc.String()
    latest_id = doc.Integer()
    latest_datetime = doc.DateTime()
    domain_id = doc.Integer()
    domain = DomainDict
    latest = ArchiveDict
    archives = doc.List(ArchiveDict)


class RetrieveURLsResponse:
    urls = doc.List(URLDict)


class PostArchiveRequest:
    url = doc.String(required=True)


class ArchiveSearchRequest:
    search_str = doc.String()
    domain = doc.String()
    offset = doc.Integer()
    limit = doc.Integer()


class ArchiveSearchResponse:
    videos = doc.List(ArchiveDict)
    totals = doc.Dictionary()
