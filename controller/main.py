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

from fastapi import FastAPI

from controller import __version__
from controller.api.schemas import (
    ConfigSummary,
    EndpointsList,
    HealthResponse,
    InfoResponse,
    RootResponse,
)
from controller.lib.config import (
    get_config,
    is_docker_mode,
    is_primary_drive_mounted,
    reload_config_from_drive,
)


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


# Root redirect to health (for now, will be UI in Phase 3)
@app.get("/", response_model=RootResponse)
async def root() -> RootResponse:
    """Root endpoint - will serve UI in Phase 3."""
    return RootResponse(
        message="WROLPi Controller",
        version=__version__,
        endpoints=EndpointsList(),
    )
