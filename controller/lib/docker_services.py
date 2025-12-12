"""
Docker container management for WROLPi Controller.

Used when running in Docker mode instead of systemd.
"""

import os

from controller.lib.config import is_docker_mode

# Import docker only if available (optional dependency)
try:
    import docker
    from docker.errors import NotFound, APIError

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None
    NotFound = Exception
    APIError = Exception

# Container name prefix (from docker-compose project)
CONTAINER_PREFIX = os.environ.get("COMPOSE_PROJECT_NAME", "wrolpi")

# Containers that should not have a "View" button (non-HTTP services)
NON_VIEWABLE_CONTAINERS = {"db", "postgres", "postgresql", "redis", "memcached"}

# Containers that should use HTTPS (in addition to *_https suffix detection)
HTTPS_CONTAINERS = {"web"}


def can_manage_containers() -> bool:
    """Check if we can manage Docker containers."""
    if not is_docker_mode():
        return False
    if not DOCKER_AVAILABLE:
        return False
    if not os.path.exists("/var/run/docker.sock"):
        return False
    return True


def _get_client():
    """Get Docker client."""
    if not DOCKER_AVAILABLE:
        raise RuntimeError("Docker library not installed")
    return docker.from_env()


def _get_container_name(service_name: str) -> str:
    """Convert service name to container name."""
    # docker-compose names: {project}-{service}-{number}
    return f"{CONTAINER_PREFIX}-{service_name}-1"


def get_container_status(name: str) -> dict:
    """
    Get status of a Docker container.

    Args:
        name: Service name

    Returns:
        dict with status info
    """
    if not can_manage_containers():
        return {
            "name": name,
            "status": "unknown",
            "available": False,
            "reason": "Docker management not available",
        }

    try:
        client = _get_client()
        container_name = _get_container_name(name)
        container = client.containers.get(container_name)

        # Map Docker status to our status
        docker_status = container.status
        if docker_status == "running":
            status = "running"
        elif docker_status == "exited":
            status = "stopped"
        elif docker_status == "restarting":
            status = "restarting"
        else:
            status = docker_status

        # Get port info from container
        ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
        port = None
        for container_port, host_bindings in ports.items():
            if host_bindings:
                port = int(host_bindings[0].get("HostPort", 0))
                break

        return {
            "name": name,
            "container_name": container_name,
            "status": status,
            "docker_status": docker_status,
            "port": port,
            "available": True,
            "viewable": name not in NON_VIEWABLE_CONTAINERS,
            "use_https": name.endswith("_https") or name in HTTPS_CONTAINERS,
        }
    except NotFound:
        return {
            "name": name,
            "status": "not_found",
            "available": True,
        }
    except Exception as e:
        return {
            "name": name,
            "status": "error",
            "error": str(e),
            "available": False,
        }


def get_all_containers_status() -> list[dict]:
    """
    Get status of all WROLPi containers.

    Returns:
        list of container status dicts
    """
    if not can_manage_containers():
        return []

    try:
        client = _get_client()
        containers = client.containers.list(all=True)

        results = []
        for container in containers:
            if container.name.startswith(CONTAINER_PREFIX):
                # Extract service name from container name
                parts = container.name.split("-")
                if len(parts) >= 2:
                    service_name = parts[1]
                else:
                    service_name = container.name

                # Get port info from container
                ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
                port = None
                for container_port, host_bindings in ports.items():
                    if host_bindings:
                        port = int(host_bindings[0].get("HostPort", 0))
                        break

                results.append({
                    "name": service_name,
                    "container_name": container.name,
                    "status": "running" if container.status == "running" else "stopped",
                    "docker_status": container.status,
                    "port": port,
                    "viewable": service_name not in NON_VIEWABLE_CONTAINERS,
                    "use_https": service_name.endswith("_https") or service_name in HTTPS_CONTAINERS,
                })

        return results
    except Exception as e:
        return [{"error": str(e)}]


def start_container(name: str) -> dict:
    """Start a Docker container."""
    if not can_manage_containers():
        return {"success": False, "error": "Docker management not available"}

    try:
        client = _get_client()
        container_name = _get_container_name(name)
        container = client.containers.get(container_name)
        container.start()
        return {"success": True, "service": name, "action": "start"}
    except NotFound:
        return {"success": False, "error": f"Container not found: {name}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def stop_container(name: str) -> dict:
    """Stop a Docker container."""
    if not can_manage_containers():
        return {"success": False, "error": "Docker management not available"}

    try:
        client = _get_client()
        container_name = _get_container_name(name)
        container = client.containers.get(container_name)
        container.stop(timeout=30)
        return {"success": True, "service": name, "action": "stop"}
    except NotFound:
        return {"success": False, "error": f"Container not found: {name}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def restart_container(name: str) -> dict:
    """Restart a Docker container."""
    if not can_manage_containers():
        return {"success": False, "error": "Docker management not available"}

    try:
        client = _get_client()
        container_name = _get_container_name(name)
        container = client.containers.get(container_name)
        container.restart(timeout=30)
        return {"success": True, "service": name, "action": "restart"}
    except NotFound:
        return {"success": False, "error": f"Container not found: {name}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_container_logs(name: str, lines: int = 100) -> dict:
    """Get logs from a Docker container."""
    if not can_manage_containers():
        return {"error": "Docker management not available"}

    try:
        client = _get_client()
        container_name = _get_container_name(name)
        container = client.containers.get(container_name)
        logs = container.logs(tail=lines).decode("utf-8")
        return {
            "service": name,
            "lines": lines,
            "logs": logs,
        }
    except NotFound:
        return {"error": f"Container not found: {name}"}
    except Exception as e:
        return {"error": str(e)}
