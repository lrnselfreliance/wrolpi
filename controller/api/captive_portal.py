"""
Captive portal routes: the landing page hotspot clients see, and the OS connectivity probes
which are redirected to it.

These live at bare paths (not under /api/) because phones request fixed URLs such as
`http://captive.apple.com/hotspot-detect.html`; the hotspot's DNS points those hostnames here.
"""
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from controller.lib.admin import get_hotspot_device, get_hotspot_ssid
from controller.lib.captive_portal import (
    PORTAL_PATH,
    PROBE_PATHS,
    get_hotspot_ip,
    is_captive_portal_enabled,
)
from controller.lib.config import is_docker_mode

logger = logging.getLogger(__name__)

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# Phones must re-probe every time; a cached redirect would show a stale portal.
NO_STORE = {"Cache-Control": "no-store"}


@router.get(PORTAL_PATH, include_in_schema=False)
async def portal(request: Request):
    """The landing page: this WROLPi's address and links to WROLPi and the Controller."""
    if is_docker_mode():
        raise HTTPException(status_code=404)
    ip = get_hotspot_ip(get_hotspot_device())
    if not ip:
        # Hotspot is down; a page with the wrong address is worse than none.
        raise HTTPException(status_code=404)
    context = {"ip": ip, "ssid": get_hotspot_ssid()}
    return templates.TemplateResponse(request, "portal.html", context, headers=NO_STORE)


async def probe():
    """A connectivity probe.  Anything but the expected reply makes the phone show the portal."""
    if not is_captive_portal_enabled():
        raise HTTPException(status_code=404)
    return RedirectResponse(url=PORTAL_PATH, status_code=302, headers=NO_STORE)


for _path in PROBE_PATHS:
    router.add_api_route(_path, probe, methods=["GET", "HEAD"], include_in_schema=False)
