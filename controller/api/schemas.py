"""
Pydantic models for Controller API requests and responses.
"""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response model for /api/health endpoint."""

    status: str = Field(description="Health status of the controller")
    version: str = Field(description="Controller version")
    docker_mode: bool = Field(description="Whether running in Docker mode")
    drive_mounted: bool = Field(description="Whether the primary drive is mounted")


class ConfigSummary(BaseModel):
    """Summary of controller configuration."""

    port: int = Field(description="Controller port")
    media_directory: str = Field(description="Path to media directory")
    managed_services_count: int = Field(description="Number of managed services")


class InfoResponse(BaseModel):
    """Response model for /api/info endpoint."""

    version: str = Field(description="Controller version")
    docker_mode: bool = Field(description="Whether running in Docker mode")
    drive_mounted: bool = Field(description="Whether the primary drive is mounted")
    config: ConfigSummary = Field(description="Configuration summary")


class EndpointsList(BaseModel):
    """List of available API endpoints."""

    health: str = Field(default="/api/health", description="Health check endpoint")
    info: str = Field(default="/api/info", description="Info endpoint")


class RootResponse(BaseModel):
    """Response model for / root endpoint."""

    message: str = Field(description="Welcome message")
    version: str = Field(description="Controller version")
    endpoints: EndpointsList = Field(description="Available endpoints")
