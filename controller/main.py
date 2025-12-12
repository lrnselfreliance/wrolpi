"""
WROLPi Controller - FastAPI Application

The Controller provides:
- System status monitoring (CPU, memory, drives, network)
- Service management (start/stop/restart systemd services)
- Disk mounting and management
- Admin operations (hotspot, throttle, shutdown, reboot)
- Simple emergency UI when main app is down
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from controller import __version__
from controller.api.schemas import (
    ConfigSummary,
    HealthResponse,
    InfoResponse,
)
from controller.api.admin import router as admin_router
from controller.api.disks import router as disks_router
from controller.api.services import router as services_router
from controller.api.status import router as status_router
from controller.lib.config import (
    get_config,
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
    get_load_status,
    get_memory_status,
    get_primary_drive_status,
)
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

    yield

    # Shutdown
    print("WROLPi Controller shutting down...")


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
    # Get real status data
    cpu = get_cpu_status()
    memory = get_memory_status()
    load = get_load_status()
    primary_drive = get_primary_drive_status()

    # Format storage data
    storage = {}
    if primary_drive:
        storage = {
            "percent": primary_drive["percent"],
            "free_gb": primary_drive["free_gb"],
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
            "temperature_c": cpu["temperature_c"],
        },
        "memory": {
            "percent": memory["percent"],
            "used_gb": memory["used_gb"],
        },
        "load": {
            "load_1min": load["load_1min"],
        },
        "storage": storage,

        # Real service status
        "services": services,
    }

    return templates.TemplateResponse(request, "index.html", context)


@app.get("/services", response_class=HTMLResponse)
async def services_page(request: Request):
    """Services management page - placeholder for Phase 6."""
    # Reuse dashboard for now - shows same data
    return await dashboard(request)


@app.get("/disks", response_class=HTMLResponse)
async def disks_page(request: Request):
    """Disk management page - placeholder for Phase 7."""
    # Reuse dashboard for now - shows same data
    return await dashboard(request)


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


@app.get("/api/info", response_model=InfoResponse)
async def get_info() -> InfoResponse:
    """
    Get Controller information and current configuration.
    """
    config = get_config()
    return InfoResponse(
        version=__version__,
        docker_mode=is_docker_mode(),
        drive_mounted=is_primary_drive_mounted(),
        config=ConfigSummary(
            port=config.get("port"),
            media_directory=config.get("media_directory"),
            managed_services_count=len(config.get("managed_services", [])),
        ),
    )
