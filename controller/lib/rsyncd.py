"""
The rsync daemon that serves this WROLPi's library to secondary WROLPis.

On a Raspberry Pi and on Debian it is the `wrolpi-rsyncd` systemd unit.  In Docker the Controller runs it in a helper
container made from the api container: the same image, user and volumes (read-only), so the media directory is
configured in one place, the api service.  Both read `controller/rsyncd.conf`.
"""

import hashlib
import logging
import re
from pathlib import Path

from controller.lib.docker_services import NotFound, _get_client, _get_container_name, can_manage_containers

logger = logging.getLogger(__name__)

RSYNCD_CONFIG = Path(__file__).parent.parent / "rsyncd.conf"
# Named like a compose service's container, so the Control page can start, stop and restart it.
HELPER_NAME = _get_container_name("rsyncd")
# What a helper was made from; a helper made from anything else is replaced.
SOURCE_LABEL = "wrolpi.rsyncd.source"
# The api image starts the API; the helper starts rsync instead.  The config arrives in the environment because the
# helper shares no directory with the Controller.
HELPER_COMMAND = 'printf "%s" "$RSYNCD_CONF" > /tmp/rsyncd.conf && exec rsync --daemon --no-detach --config=/tmp/rsyncd.conf'


def read_rsyncd_config() -> str:
    return RSYNCD_CONFIG.read_text()


def get_rsyncd_port(config: str = None) -> int:
    """The port in rsyncd.conf, so the published port cannot differ from the one the daemon listens on."""
    match = re.search(r"^port\s*=\s*(\d+)\s*$", config or read_rsyncd_config(), re.MULTILINE)
    if not match:
        raise RuntimeError(f"No port in {RSYNCD_CONFIG}")
    return int(match.group(1))


def ensure_rsync_daemon() -> dict:
    """Docker only: make sure the helper container serves the api container's volumes.

    A helper made from this api container, image and config is left alone (started if it stopped); any other is
    replaced.  Never raises: a WROLPi without the daemon still works, it only cannot be copied by a secondary."""
    if not can_manage_containers():
        return {"success": False, "error": "Docker management not available"}

    try:
        client = _get_client()
        config = read_rsyncd_config()
        port = get_rsyncd_port(config)
        api = client.containers.get(_get_container_name("api"))
        source = hashlib.sha256(f"{api.id}:{api.image.id}:{config}".encode()).hexdigest()

        try:
            helper = client.containers.get(HELPER_NAME)
        except NotFound:
            helper = None
        if helper is not None:
            if helper.labels.get(SOURCE_LABEL) == source:
                if helper.status != "running":
                    logger.info("Starting the rsync daemon container %s", HELPER_NAME)
                    helper.start()
                return {"success": True, "action": "kept"}
            logger.info("Replacing the rsync daemon container %s", HELPER_NAME)
            helper.remove(force=True)

        client.containers.run(
            api.image.id,
            ["-c", HELPER_COMMAND],
            entrypoint="sh",
            name=HELPER_NAME,
            detach=True,
            user=api.attrs["Config"].get("User") or None,
            volumes_from=[f"{api.name}:ro"],
            ports={f"{port}/tcp": port},
            environment={"RSYNCD_CONF": config},
            labels={SOURCE_LABEL: source},
            restart_policy={"Name": "unless-stopped"},
        )
        logger.info("Started the rsync daemon container %s on port %s", HELPER_NAME, port)
        return {"success": True, "action": "created"}
    except Exception as e:
        # For example an api image built before rsync was added to it.
        logger.warning("Could not start the rsync daemon container: %s", e)
        return {"success": False, "error": str(e)}
