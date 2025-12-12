"""
Pydantic models for Controller API requests and responses.
"""

from typing import Optional

from pydantic import BaseModel, Field


# ============================================================================
# Health
# ============================================================================

class HealthResponse(BaseModel):
    """Response model for /api/health endpoint."""

    status: str = Field(description="Health status of the controller")
    version: str = Field(description="Controller version")
    docker_mode: bool = Field(description="Whether running in Docker mode")
    drive_mounted: bool = Field(description="Whether the primary drive is mounted")


# ============================================================================
# Status - CPU
# ============================================================================

class CpuStatusResponse(BaseModel):
    """Response model for /api/stats/cpu endpoint."""

    percent: float = Field(description="CPU usage percentage (0-100)")
    frequency_mhz: Optional[int] = Field(default=None, description="Current CPU frequency in MHz")
    frequency_max_mhz: Optional[int] = Field(default=None, description="Maximum CPU frequency in MHz")
    temperature_c: Optional[float] = Field(default=None, description="CPU temperature in Celsius")
    cores: int = Field(description="Number of CPU cores")


# ============================================================================
# Status - Memory
# ============================================================================

class MemoryStatusResponse(BaseModel):
    """Response model for /api/stats/memory endpoint."""

    total_bytes: int = Field(description="Total memory in bytes")
    available_bytes: int = Field(description="Available memory in bytes")
    used_bytes: int = Field(description="Used memory in bytes")
    percent: float = Field(description="Memory usage percentage (0-100)")
    total_gb: float = Field(description="Total memory in GB")
    used_gb: float = Field(description="Used memory in GB")
    available_gb: float = Field(description="Available memory in GB")


# ============================================================================
# Status - Load
# ============================================================================

class LoadStatusResponse(BaseModel):
    """Response model for /api/stats/load endpoint."""

    load_1min: float = Field(description="1-minute load average")
    load_5min: float = Field(description="5-minute load average")
    load_15min: float = Field(description="15-minute load average")


# ============================================================================
# Status - Drives
# ============================================================================

class DriveStatusResponse(BaseModel):
    """Response model for individual drive status."""

    device: str = Field(description="Device path (e.g., /dev/sda1)")
    mount_point: str = Field(description="Mount point path")
    fstype: str = Field(description="Filesystem type")
    total_bytes: int = Field(description="Total space in bytes")
    used_bytes: int = Field(description="Used space in bytes")
    free_bytes: int = Field(description="Free space in bytes")
    percent: float = Field(description="Usage percentage (0-100)")
    total_gb: float = Field(description="Total space in GB")
    used_gb: float = Field(description="Used space in GB")
    free_gb: float = Field(description="Free space in GB")


class PrimaryDriveStatusResponse(BaseModel):
    """Response model for /api/stats/drives/primary endpoint."""

    mounted: bool = Field(description="Whether the primary drive is mounted")
    device: Optional[str] = Field(default=None, description="Device path")
    mount_point: Optional[str] = Field(default=None, description="Mount point path")
    fstype: Optional[str] = Field(default=None, description="Filesystem type")
    total_bytes: Optional[int] = Field(default=None, description="Total space in bytes")
    used_bytes: Optional[int] = Field(default=None, description="Used space in bytes")
    free_bytes: Optional[int] = Field(default=None, description="Free space in bytes")
    percent: Optional[float] = Field(default=None, description="Usage percentage")
    total_gb: Optional[float] = Field(default=None, description="Total space in GB")
    used_gb: Optional[float] = Field(default=None, description="Used space in GB")
    free_gb: Optional[float] = Field(default=None, description="Free space in GB")


# ============================================================================
# Status - Network
# ============================================================================

class NetworkInterfaceResponse(BaseModel):
    """Response model for individual network interface."""

    name: str = Field(description="Interface name (e.g., eth0, wlan0)")
    ipv4: Optional[str] = Field(default=None, description="IPv4 address")
    ipv6: Optional[str] = Field(default=None, description="IPv6 address")
    mac: Optional[str] = Field(default=None, description="MAC address")
    bytes_sent: int = Field(description="Total bytes sent")
    bytes_recv: int = Field(description="Total bytes received")
    bytes_sent_mb: float = Field(description="Total MB sent")
    bytes_recv_mb: float = Field(description="Total MB received")


# ============================================================================
# Status - Power
# ============================================================================

class PowerStatusResponse(BaseModel):
    """Response model for /api/stats/power endpoint."""

    undervoltage_detected: bool = Field(description="Currently experiencing undervoltage")
    currently_throttled: bool = Field(description="Currently throttled due to voltage/temp")
    undervoltage_occurred: bool = Field(description="Undervoltage has occurred since boot")
    throttling_occurred: bool = Field(description="Throttling has occurred since boot")


# ============================================================================
# Status - Full
# ============================================================================

class FullStatusResponse(BaseModel):
    """Response model for /api/stats endpoint."""

    cpu: CpuStatusResponse = Field(description="CPU status")
    memory: MemoryStatusResponse = Field(description="Memory status")
    load: LoadStatusResponse = Field(description="System load")
    drives: list[DriveStatusResponse] = Field(description="All mounted drives")
    primary_drive: Optional[DriveStatusResponse] = Field(default=None, description="Primary WROLPi drive")
    network: list[NetworkInterfaceResponse] = Field(description="Network interfaces")
    power: PowerStatusResponse = Field(description="Power status")


# ============================================================================
# Admin - Hotspot
# ============================================================================

class HotspotStatusResponse(BaseModel):
    """Response model for /api/hotspot/status endpoint."""

    enabled: bool = Field(description="Whether hotspot is currently enabled")
    available: bool = Field(description="Whether hotspot functionality is available")
    reason: Optional[str] = Field(default=None, description="Reason if unavailable")
    ssid: Optional[str] = Field(default=None, description="Hotspot SSID when enabled")
    device: Optional[str] = Field(default=None, description="WiFi device name")


class HotspotActionResponse(BaseModel):
    """Response model for hotspot enable/disable actions."""

    success: bool = Field(description="Whether the action succeeded")
    ssid: Optional[str] = Field(default=None, description="Hotspot SSID")
    device: Optional[str] = Field(default=None, description="WiFi device name")
    error: Optional[str] = Field(default=None, description="Error message if failed")


# ============================================================================
# Admin - Throttle
# ============================================================================

class ThrottleStatusResponse(BaseModel):
    """Response model for /api/throttle/status endpoint."""

    enabled: bool = Field(description="Whether CPU throttle (powersave) is enabled")
    available: bool = Field(description="Whether throttle control is available")
    reason: Optional[str] = Field(default=None, description="Reason if unavailable")
    governor: Optional[str] = Field(default=None, description="Current CPU governor")
    available_governors: Optional[list[str]] = Field(default=None, description="Available governors")


class ThrottleActionResponse(BaseModel):
    """Response model for throttle enable/disable actions."""

    success: bool = Field(description="Whether the action succeeded")
    governor: Optional[str] = Field(default=None, description="New CPU governor")
    error: Optional[str] = Field(default=None, description="Error message if failed")


# ============================================================================
# Admin - System Control
# ============================================================================

class SystemActionResponse(BaseModel):
    """Response model for system shutdown/reboot actions."""

    success: bool = Field(description="Whether the action was initiated")
    message: Optional[str] = Field(default=None, description="Status message")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class ServiceRestartResult(BaseModel):
    """Result of restarting a single service."""

    success: bool = Field(description="Whether the service restart succeeded")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    pending: Optional[bool] = Field(default=None, description="Whether restart is pending")


class RestartServicesResponse(BaseModel):
    """Response model for /api/restart endpoint."""

    success: bool = Field(description="Whether the restart was initiated")
    services: dict[str, ServiceRestartResult] = Field(description="Results per service")
    error: Optional[str] = Field(default=None, description="Error message if failed")


# ============================================================================
# Services - Status
# ============================================================================

class ServiceStatusResponse(BaseModel):
    """Response model for individual service status."""

    name: str = Field(description="Service name")
    status: str = Field(description="Service status (running, stopped, failed, unknown)")
    systemd_name: Optional[str] = Field(default=None, description="Systemd unit name")
    container_name: Optional[str] = Field(default=None, description="Docker container name")
    active: Optional[str] = Field(default=None, description="Systemd active state")
    docker_status: Optional[str] = Field(default=None, description="Docker container status")
    enabled: Optional[bool] = Field(default=None, description="Whether service starts at boot")
    port: Optional[int] = Field(default=None, description="Service port")
    viewable: Optional[bool] = Field(default=False, description="Whether service has a web UI")
    view_path: Optional[str] = Field(default="", description="Path to web UI")
    use_https: Optional[bool] = Field(default=False, description="Whether service uses HTTPS")
    description: Optional[str] = Field(default="", description="Service description")
    available: Optional[bool] = Field(default=None, description="Whether management is available")
    reason: Optional[str] = Field(default=None, description="Reason if unavailable")
    error: Optional[str] = Field(default=None, description="Error message if any")


class ServiceActionResponse(BaseModel):
    """Response model for service start/stop/restart/enable/disable actions."""

    success: bool = Field(description="Whether the action succeeded")
    service: str = Field(description="Service name")
    action: str = Field(description="Action performed (start, stop, restart, enable, disable)")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class ServiceLogsResponse(BaseModel):
    """Response model for service logs."""

    service: str = Field(description="Service name")
    lines: int = Field(description="Number of lines requested")
    since: Optional[str] = Field(default=None, description="Time filter if specified")
    logs: str = Field(description="Log content")


class ServicesListErrorResponse(BaseModel):
    """Response model when services list fails."""

    error: str = Field(description="Error message")
    reason: Optional[str] = Field(default=None, description="Detailed reason")
