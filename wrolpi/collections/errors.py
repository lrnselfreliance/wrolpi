from wrolpi.errors import APIError

__all__ = ['UnknownCollection']


class UnknownCollection(APIError):
    """Cannot find Collection"""
    code = 'UNKNOWN_COLLECTION'
    summary = 'Cannot find Collection'
