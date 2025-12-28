import logging


class EmptyMessageFilter(logging.Filter):
    """Used to filter empty messages that Sanic's access log emits."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.msg
        try:
            if not message:
                return False
            if not message.strip():
                return False
            return True
        except AttributeError:
            # message.strip does not exist when restarting the service, ignore it.
            return False
