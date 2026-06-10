from wrolpi.errors import APIError, UnknownCollection

__all__ = ['UnknownCollection', 'ReorganizationConflict']


class ReorganizationConflict(APIError):
    """Reorganization would cause filename conflicts"""
    code = 'REORGANIZATION_CONFLICT'
    summary = 'Reorganization would cause filename conflicts'
