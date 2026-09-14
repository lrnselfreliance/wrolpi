"""
Captive portal routes: the landing page hotspot clients see, and the OS connectivity probes
which are redirected to it.

These live at bare paths (not under /api/) because phones request fixed URLs such as
`http://captive.apple.com/hotspot-detect.html`; the hotspot's DNS points those hostnames here.
"""
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from controller.lib.admin import get_hotspot_device, get_hotspot_ssid
from controller.lib.captive_portal import (
    PORTAL_CONTINUE_PATH,
    PORTAL_PATH,
    PROBE_PATHS,
    PROBE_SUCCESS_RESPONSES,
    acknowledge_client,
    get_hotspot_ip,
    is_captive_portal_enabled,
    is_client_acknowledged,
)
from controller.lib.config import is_docker_mode

logger = logging.getLogger(__name__)

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# Phones must re-probe every time; a cached redirect would show a stale portal.
NO_STORE = {"Cache-Control": "no-store"}


def _render_portal(request: Request, connected: bool):
    if is_docker_mode():
        raise HTTPException(status_code=404)
    ip = get_hotspot_ip(get_hotspot_device())
    if not ip:
        # Hotspot is down; a page with the wrong address is worse than none.
        raise HTTPException(status_code=404)
    context = {"ip": ip, "ssid": get_hotspot_ssid(), "connected": connected,
               "continue_path": PORTAL_CONTINUE_PATH}
    return templates.TemplateResponse(request, "portal.html", context, headers=NO_STORE)


@router.get(PORTAL_PATH, include_in_schema=False)
async def portal(request: Request):
    """The welcome page: this WROLPi's address and a Continue button."""
    return _render_portal(request, connected=False)


@router.get(PORTAL_CONTINUE_PATH, include_in_schema=False)
async def portal_continue(request: Request):
    """
    The page after Continue.  The phone re-probes after this navigation; the client is now
    acknowledged so that probe succeeds and the sheet offers "Done".
    """
    response = _render_portal(request, connected=True)  # 404s first if the hotspot is down
    acknowledge_client(request.client.host if request.client else None)
    return response


async def probe(request: Request):
    """
    A connectivity probe.  Anything but the expected reply makes the phone show the portal, so
    redirect until this client has tapped Continue on the portal, then give the reply it expects.
    """
    if not is_captive_portal_enabled():
        raise HTTPException(status_code=404)
    if is_client_acknowledged(request.client.host if request.client else None):
        status, media_type, body = PROBE_SUCCESS_RESPONSES[request.url.path]
        return Response(content=body, status_code=status, media_type=media_type, headers=NO_STORE)
    return RedirectResponse(url=PORTAL_PATH, status_code=302, headers=NO_STORE)


for _path in PROBE_PATHS:
    router.add_api_route(_path, probe, methods=["GET", "HEAD"], include_in_schema=False)
