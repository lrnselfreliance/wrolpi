from sanic_openapi import doc


class FilesRequest:
    directories = doc.List(doc.String())


class DeleteRequest:
    file = doc.String()
