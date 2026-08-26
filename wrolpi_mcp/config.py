"""Configuration for the WROLPi MCP server."""
import os

# WROLPi API base URL.  Override with WROLPI_API_URL environment variable.
API_BASE_URL = os.environ.get("WROLPI_API_URL", "https://localhost:8443")

# Whether to verify TLS certificates (WROLPi uses self-signed certs locally).
VERIFY_TLS = os.environ.get("WROLPI_VERIFY_TLS", "false").lower() in ("true", "1", "yes")

# Default search result limit.
DEFAULT_LIMIT = 10
