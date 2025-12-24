"""
WROLPi Controller - FastAPI Application

The Controller provides:
- System status monitoring (CPU, memory, drives, network)
- Service management (start/stop/restart systemd services)
- Disk mounting and management
- Admin operations (hotspot, throttle, shutdown, reboot)
- Simple emergency UI when main app is down
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from controller import __version__
from controller.api.admin import router as admin_router
from controller.api.disks import router as disks_router
from controller.api.schemas import HealthResponse
from controller.api.services import router as services_router
from controller.api.status import router as status_router
from controller.lib.config import (
    is_docker_mode,
    is_primary_drive_mounted,
    reload_config_from_drive,
)
from controller.lib.docker_services import (
    can_manage_containers,
    get_all_containers_status,
)
from controller.lib.status import (
    get_cpu_status,
    get_iostat_status,
    get_load_status,
    get_memory_status,
    get_primary_drive_status,
)
from controller.lib.status_worker import status_worker_loop
from controller.lib.systemd import get_all_services_status

# Templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Runs on startup and shutdown.
    """
    # Startup
    print(f"WROLPi Controller v{__version__} starting...")
    print(f"Docker mode: {is_docker_mode()}")

    # Try to load config from drive if mounted
    if is_primary_drive_mounted():
        if reload_config_from_drive():
            print("Loaded configuration from drive")
        else:
            print("Using default configuration (no controller.yaml found)")
    else:
        print("Primary drive not mounted - using default configuration")

    # Initialize cached status
    app.state.cached_status = {}

    # Start status worker background task
    status_task = asyncio.create_task(status_worker_loop(app))

    yield

    # Shutdown
    print("WROLPi Controller shutting down...")
    status_task.cancel()
    try:
        await status_task
    except asyncio.CancelledError:
        pass


# Create FastAPI app
app = FastAPI(
    title="WROLPi Controller",
    description="System management service for WROLPi",
    version=__version__,
    lifespan=lifespan,
)

# Include routers
app.include_router(admin_router)
app.include_router(disks_router)
app.include_router(services_router)
app.include_router(status_router)


def get_host(request: Request) -> str:
    """Get the host for links (use request host, fallback to localhost)."""
    host = request.headers.get("host", "localhost")
    # Strip port if present
    if ":" in host:
        host = host.split(":")[0]
    return host


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render the main dashboard UI with real status data."""
    # Try to use cached status first
    cached = getattr(request.app.state, "cached_status", {})

    if cached:
        cpu = cached.get("cpu_stats") or {}
        memory = cached.get("memory_stats") or {}
        load = cached.get("load_stats") or {}
        iostat = cached.get("iostat_stats") or {}
        drives = cached.get("drives_stats") or []
        primary_drive = None
        for drive in drives:
            if drive.get("mount") == "/media/wrolpi":
                primary_drive = drive
                break
    else:
        # Fallback to direct calls if cache not yet populated
        cpu = get_cpu_status()
        memory = get_memory_status()
        load = get_load_status()
        iostat = get_iostat_status()
        primary_drive = get_primary_drive_status()

    # Format storage data
    storage = {}
    if primary_drive:
        free_bytes = primary_drive["size"] - primary_drive["used"]
        storage = {
            "percent": primary_drive["percent"],
            "free_gb": round(free_bytes / (1024 ** 3), 1),
        }

    # Get service status
    if is_docker_mode():
        if can_manage_containers():
            services = get_all_containers_status()
        else:
            services = []
    else:
        services = get_all_services_status()

    context = {
        "version": __version__,
        "docker_mode": is_docker_mode(),
        "drive_mounted": is_primary_drive_mounted(),
        "host": get_host(request),

        # Real status data
        "cpu": {
            "percent": cpu["percent"],
            "temperature_c": cpu["temperature"],  # Field renamed
        },
        "memory": {
            "percent": round((memory["used"] / memory["total"]) * 100, 1) if memory["total"] > 0 else 0,
            "used_gb": round(memory["used"] / (1024 ** 3), 1),
        },
        "load": {
            "load_1min": load["minute_1"],  # Field renamed
        },
        "storage": storage,
        "iostat": {
            "percent_iowait": iostat.get("percent_iowait"),
        },

        # Real service status
        "services": services,
    }

    return templates.TemplateResponse(request, "index.html", context)


@app.get("/api/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.
    Returns basic status for monitoring and load balancer checks.
    """
    return HealthResponse(
        status="healthy",
        version=__version__,
        docker_mode=is_docker_mode(),
        drive_mounted=is_primary_drive_mounted(),
    )
