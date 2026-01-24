from wrolpi.errors import APIError

__all__ = ['UnknownCollection', 'ReorganizationConflict']


class UnknownCollection(APIError):
    """Cannot find Collection"""
    code = 'UNKNOWN_COLLECTION'
    summary = 'Cannot find Collection'


class ReorganizationConflict(APIError):
    """Reorganization would cause filename conflicts"""
    code = 'REORGANIZATION_CONFLICT'
    summary = 'Reorganization would cause filename conflicts'
