"""
Tests for readiness check functions.
"""

from unittest import mock

import aiohttp
import pytest

from controller.lib.readiness import (
    _get_api_url,
    _get_app_url,
    check_api_ready,
    check_app_ready,
)


class TestReadinessUrls:

    def test_api_url_docker_mode(self):
        with mock.patch("controller.lib.readiness.is_docker_mode", return_value=True):
            assert _get_api_url() == "http://api:8081/api/echo"

    def test_api_url_systemd_mode(self):
        with mock.patch("controller.lib.readiness.is_docker_mode", return_value=False):
            assert _get_api_url() == "http://127.0.0.1:8081/api/echo"

    def test_app_url_docker_mode(self):
        with mock.patch("controller.lib.readiness.is_docker_mode", return_value=True):
            assert _get_app_url() == "http://app:3000"

    def test_app_url_systemd_mode(self):
        with mock.patch("controller.lib.readiness.is_docker_mode", return_value=False):
            assert _get_app_url() == "http://127.0.0.1:3000"


@pytest.mark.asyncio
class TestReadinessChecks:

    async def test_check_api_ready_returns_false_on_connection_error(self):
        with mock.patch("aiohttp.ClientSession.get", side_effect=aiohttp.ClientError()):
            result = await check_api_ready()
            assert result is False

    async def test_check_app_ready_returns_false_on_connection_error(self):
        with mock.patch("aiohttp.ClientSession.get", side_effect=aiohttp.ClientError()):
            result = await check_app_ready()
            assert result is False
