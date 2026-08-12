"""
The map overview blob must reach `/opt/wrolpi-blobs` in the Docker deployment.

The React map viewer draws the world at zoom 0-6 from `/blobs/map-overview.pmtiles`, which
Caddy serves out of `/opt/wrolpi-blobs`.  A user who subscribes to regional extracts -- the
normal case, since the planet file is 134GB -- gets that blob and nothing else underneath
their regions, so when it is missing the regions float on an empty background and the map
reads as broken.

Raspberry Pi and Debian installs get the blob from pi-gen, the live-build config, and
upgrade.sh.  Docker had no equivalent: the compose file bind-mounted a git-ignored (and
therefore empty) host directory over `/opt/wrolpi-blobs`, so the path existed and was empty
on every Docker WROLPi.  Verified on a running deployment -- `/blobs/map-overview.pmtiles`
returned 404 while the same URL returned 206 on hardware.

These read the deployment files rather than a running container: building the image to check
takes a CDN download and several minutes, and the two things that actually broke -- nothing
fetches the blob, and a mount hides it -- are both visible in the source.
"""
from pathlib import Path

import pytest
import yaml

from wrolpi.vars import PROJECT_DIR

BLOBS_DIR = '/opt/wrolpi-blobs'
OVERVIEW_NAME = 'map-overview.pmtiles'

WEB_DOCKERFILE = PROJECT_DIR / 'docker/web/Dockerfile'
COMPOSE_FILE = PROJECT_DIR / 'docker-compose.yml'
WEB_CADDYFILE = PROJECT_DIR / 'docker/web/Caddyfile'


@pytest.fixture
def web_dockerfile() -> str:
    return WEB_DOCKERFILE.read_text()


@pytest.fixture
def compose() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text())


def test_files_exist():
    """The premise.  A missing file would read exactly like a passing test below."""
    for path in (WEB_DOCKERFILE, COMPOSE_FILE, WEB_CADDYFILE):
        assert path.is_file(), f'{path} is missing'


def test_web_caddy_serves_blobs_from_the_blobs_directory():
    """The premise for the rest: `/blobs/*` really is `/opt/wrolpi-blobs`."""
    caddyfile = WEB_CADDYFILE.read_text()
    assert 'handle_path /blobs/*' in caddyfile
    assert BLOBS_DIR in caddyfile


def test_web_image_provisions_the_map_overview_blob(web_dockerfile):
    """The web image must put the overview blob at the path Caddy serves."""
    assert OVERVIEW_NAME in web_dockerfile, \
        f'docker/web/Dockerfile never provisions {OVERVIEW_NAME}; a Docker WROLPi with only ' \
        f'regional map files will have no world basemap'
    assert f'{BLOBS_DIR}/{OVERVIEW_NAME}' in web_dockerfile


def test_web_image_fails_the_build_when_the_blob_is_missing(web_dockerfile):
    """
    A silent failure here is the whole bug: an image that builds without the blob ships and
    the map is broken at runtime, where nothing explains why.  pi-gen and the live-build
    config both hard-fail on this, so the Docker build does too.
    """
    fetch = [line for line in web_dockerfile.splitlines() if OVERVIEW_NAME in line]
    assert fetch, 'no line mentions the overview blob'
    # `curl -f` turns an HTTP error into a non-zero exit, which fails the RUN layer.  Without
    # it curl writes the error body to the output file and exits 0.
    assert any('curl -f' in line or 'curl --fail' in line for line in fetch), \
        'the blob download must use curl -f so an HTTP error fails the build'


def test_compose_does_not_shadow_the_blobs_directory(compose):
    """
    A bind mount over `/opt/wrolpi-blobs` replaces what the image provides -- it does not
    merge with it.  The compose file mounted a git-ignored host directory there, so the blob
    baked into the image would be invisible even once the Dockerfile fetches it.  This is the
    assertion that fails on the original code.
    """
    volumes = compose['services']['web'].get('volumes') or []
    for volume in volumes:
        # Entries are "source:target" or "source:target:mode".
        target = volume.split(':')[1] if ':' in volume else ''
        assert target != BLOBS_DIR, \
            f'docker-compose.yml mounts {volume!r} over {BLOBS_DIR}, hiding the ' \
            f'{OVERVIEW_NAME} baked into the web image'


def test_no_git_ignored_blobs_directory_is_relied_upon():
    """
    The host `./blobs` directory this used to mount is in .gitignore, so it is empty on every
    fresh clone.  Nothing in the deployment should depend on a user populating it by hand.
    """
    gitignore = (PROJECT_DIR / '.gitignore').read_text()
    if '/blobs/' not in gitignore:
        pytest.skip('./blobs is no longer git-ignored')
    compose_text = COMPOSE_FILE.read_text()
    assert './blobs:' not in compose_text, \
        './blobs is git-ignored and therefore empty; the compose file must not depend on it'


def test_pi_and_docker_agree_on_the_blob_location():
    """
    Hardware and Docker must serve the same URL from the same path, or a fix to one silently
    leaves the other broken -- which is exactly how this shipped.
    """
    pi_caddyfile = (PROJECT_DIR / 'etc/raspberrypios/Caddyfile').read_text()
    docker_caddyfile = WEB_CADDYFILE.read_text()
    for caddyfile in (pi_caddyfile, docker_caddyfile):
        assert 'handle_path /blobs/*' in caddyfile
        assert f'root * {BLOBS_DIR}' in caddyfile
