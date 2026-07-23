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
import logging
from contextlib import asynccontextmanager
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from controller import __version__
from fastapi.middleware.cors import CORSMiddleware

from controller.api.admin import router as admin_router
from controller.api.disks import router as disks_router
from controller.api.onboarding import router as onboarding_router
from controller.api.ready import router as ready_router
from controller.api.schemas import HealthResponse
from controller.api.scripts import router as scripts_router
from controller.api.services import router as services_router
from controller.api.status import router as status_router
from controller.lib.config import (
    get_ca_certificate_path,
    get_config_value,
    is_ca_certificate_available,
    is_docker_mode,
    is_primary_drive_mounted,
    reload_config_from_drive,
    save_config,
    update_config,
)
from controller.lib.scripts import get_script_status
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
    get_uptime_status,
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
    logger.info("WROLPi Controller v%s starting...", __version__)
    logger.info("Docker mode: %s", is_docker_mode())

    # When running under Docker dev, status.py will have already remapped
    # psutil.PROCFS_PATH to /host/proc (and the sysfs paths) so we report
    # real host metrics instead of the container's tiny namespace.
    if is_docker_mode():
        import psutil
        procfs_path = getattr(psutil, "PROCFS_PATH", "N/A (not supported on this platform)")
        logger.info("Using host procfs for stats: %s", procfs_path)

    # Try to load config from drive if mounted
    if is_primary_drive_mounted():
        if reload_config_from_drive():
            logger.info("Loaded configuration from drive")
        else:
            logger.info("Using default configuration (no controller.yaml found)")

        # Apply timezone from wrolpi.yaml to the system.
        from controller.lib.admin import apply_timezone_from_config, migrate_hotspot_settings_from_wrolpi_config
        apply_timezone_from_config()

        # Copy legacy hotspot settings from wrolpi.yaml into controller.yaml.
        migrate_hotspot_settings_from_wrolpi_config()

        # Apply Samba config if enabled.
        from controller.lib.samba import apply_samba_from_config
        apply_samba_from_config()
    else:
        # Drive may be mounted but controller.yaml may not exist yet (e.g., the system
        # was set up before the Controller was introduced). Create the marker file.
        from controller.lib.config import get_media_directory, save_config
        media_dir = get_media_directory()
        if media_dir.is_mount():
            logger.info("Primary drive is mounted at %s but controller.yaml is missing, creating it", media_dir)
            config_dir = media_dir / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            try:
                save_config()
                reload_config_from_drive()
            except RuntimeError as e:
                logger.warning("Failed to create controller.yaml: %s", e)

            from controller.lib.admin import apply_timezone_from_config, migrate_hotspot_settings_from_wrolpi_config
            apply_timezone_from_config()
            migrate_hotspot_settings_from_wrolpi_config()

            from controller.lib.samba import apply_samba_from_config
            apply_samba_from_config()
        else:
            logger.info("Primary drive not mounted - using default configuration")

    # Initialize cached status
    app.state.cached_status = {}

    # Start status worker background task
    status_task = asyncio.create_task(status_worker_loop(app))

    yield

    # Shutdown
    logger.info("WROLPi Controller shutting down...")
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

# CORS middleware - matches Caddy's permissive policy for offline/local use.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(admin_router)
app.include_router(disks_router)
app.include_router(onboarding_router)
app.include_router(ready_router)
app.include_router(scripts_router)
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
        uptime = cached.get("uptime_stats") or {}
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
        uptime = get_uptime_status()
        primary_drive = get_primary_drive_status()

    # Format storage data
    storage = {}
    if primary_drive:
        free_bytes = primary_drive["size"] - primary_drive["used"]
        storage = {
            "percent": primary_drive["percent"],
            "free_gb": round(free_bytes / (1024 ** 3), 1),
        }

    # Format uptime
    uptime_seconds = uptime.get("uptime_seconds", 0)
    if uptime_seconds:
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        uptime_formatted = f"{days}d {hours}h" if days > 0 else f"{hours}h {(uptime_seconds % 3600) // 60}m"
    else:
        uptime_formatted = "--"

    # Get service status
    if is_docker_mode():
        if can_manage_containers():
            services = get_all_containers_status()
        else:
            services = []
    else:
        services = get_all_services_status()

    # Sort services so problems surface first, then alphabetically. The
    # template partitions on each service's "group" (core vs optional).
    _status_order = {"failed": 0, "unknown": 1, "stopped": 2, "running": 3}
    services = sorted(
        services,
        key=lambda s: (_status_order.get(s.get("status"), 1), s["name"]),
    )

    # Root CA download is only useful after the media drive is mounted (so an
    # existing CA on the drive is visible) and repair has finished generating
    # or refreshing certificates. While repair is running the CA may not exist
    # yet or the leaf/Caddyfile may still be mid-update.
    script_status = get_script_status()
    repair_running = (
        script_status.get("running") and script_status.get("script_name") == "repair"
    )
    cert_download_ready = is_ca_certificate_available() and not repair_running

    context = {
        "version": __version__,
        "docker_mode": is_docker_mode(),
        "drive_mounted": is_primary_drive_mounted(),
        "hide_cert_banner": get_config_value("hide_cert_banner", False),
        "cert_download_ready": cert_download_ready,
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
        "uptime": {
            "formatted": uptime_formatted,
            "seconds": uptime_seconds,
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


@app.get("/ca.crt")
async def download_ca_certificate():
    """Serve the WROLPi Root CA certificate for browser trust setup.

    Only available after the media drive is mounted so an existing CA on the
    drive can be served (and never a transient pre-onboarding path).
    """
    from fastapi.responses import JSONResponse

    if not is_docker_mode() and not is_primary_drive_mounted():
        return JSONResponse(
            status_code=404,
            content={"error": "CA certificate not available until the media drive is mounted"},
        )
    ca_path = get_ca_certificate_path()
    if not ca_path.is_file():
        return JSONResponse(status_code=404, content={"error": "CA certificate not found"})
    return FileResponse(
        path=ca_path,
        media_type="application/x-x509-ca-cert",
        filename="wrolpi-ca.crt",
        headers={"Content-Disposition": 'attachment; filename="wrolpi-ca.crt"'},
    )


@app.post("/api/hide-cert-banner")
async def hide_cert_banner():
    """Permanently hide the HTTPS certificate setup banner."""
    update_config("hide_cert_banner", True)
    save_config()
    return {"ok": True}
