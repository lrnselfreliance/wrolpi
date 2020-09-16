from sanic_openapi import doc


class PBFPostRequest:
    pbf_url = doc.String()


class PBFPostResponse:
    success = doc.String()
