"""The shared progress record of a secondary WROLPi's sync, `api_app.shared_ctx.status['sync']`.

It lives in a manager dict, so every read returns a copy: change it only with `update_sync_status`.
"""


def default_sync_status() -> dict:
    return dict(
        state='idle',
        phase=None,
        requested=False,
        force=False,
        cancel_requested=False,
        started_at=None,
        finished_at=None,
        last_success_at=None,
        last_error=None,
        last_skip_reason=None,
        primary_url=None,
        primary_version=None,
        groups_seen=0,
        max_id=0,
        files_checked=0,
        files_to_download=0,
        files_downloaded=0,
        bytes_downloaded=0,
        files_failed=0,
        configs_imported=[],
        disk_full=False,
    )


def get_sync_status() -> dict:
    from wrolpi.api_utils import api_app
    return dict(api_app.shared_ctx.status.get('sync') or default_sync_status())


def update_sync_status(**changes) -> dict:
    """Merge `changes` into the shared sync status.  Only the perpetual process and the sync endpoints write it, and
    the endpoints only set the request/cancel keys, so a lost update can only delay a request by one tick."""
    from wrolpi.api_utils import api_app
    status = get_sync_status()
    status.update(changes)
    api_app.shared_ctx.status['sync'] = status
    return status
