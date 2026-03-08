"""
Readiness API endpoint for WROLPi Controller.

Allows the controller UI to check if the main API and React app are up
without making cross-origin browser requests.
"""

import asyncio

from fastapi import APIRouter

from controller.api.schemas import ReadyResponse
from controller.lib.readiness import check_api_ready, check_app_ready

router = APIRouter(tags=["readiness"])


@router.get("/api/ready", response_model=ReadyResponse)
async def readiness_check() -> ReadyResponse:
    """
    Check if the main WROLPi API and React app are responding.

    Performs server-side HTTP requests to avoid CORS and certificate issues
    that arise from browser-based cross-origin fetch requests.
    """
    api_ready, app_ready = await asyncio.gather(
        check_api_ready(),
        check_app_ready(),
    )
    return ReadyResponse(api=api_ready, app=app_ready)
