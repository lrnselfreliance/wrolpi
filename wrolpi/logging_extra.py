import logging


class EmptyMessageFilter(logging.Filter):
    """Used to filter empty messages that Sanic's access log emits."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.msg
        if not message:
            return False
        if not message.strip():
            return False
        return True
