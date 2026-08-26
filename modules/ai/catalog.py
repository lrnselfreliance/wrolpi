"""The AI model catalog.

The bundled AI_MODELS constant is the offline fallback (like the map module's MAP_REGIONS);
the CDN manifest at ai/models.json is fetched at browse/download time and GPG-verified with the
committed WROLPi public key.  The release process refreshes AI_MODELS from the published manifest.
"""
import json
import tempfile
from pathlib import Path

import psutil

from wrolpi.common import aiohttp_get, get_media_directory, logger, verify_gpg_signature

logger = logger.getChild(__name__)

CDN = 'https://wrolpi.nyc3.cdn.digitaloceanspaces.com'
MODELS_MANIFEST_URL = f'{CDN}/ai/models.json'

# Sizes are bytes; sha256 values are filled from the published manifest at release time.  The
# meta4 sidecar (GPG-verified at download time) is what actually enforces the hash.
AI_MODELS = [
    dict(
        name='Qwen3-1.7B-Q4_K_M.gguf',
        tier='small',
        url=f'{CDN}/ai/Qwen3-1.7B-Q4_K_M.gguf',
        sha256='',
        size=1_200_000_000,
        min_ram_gb=4,
        default_context=8_192,
        license='Apache 2.0',
        description='The default assistant for 4GB devices (Pi 4/5). Best tool-calling per byte.',
    ),
    dict(
        name='Qwen3-4B-Instruct-2507-Q4_K_M.gguf',
        tier='medium',
        url=f'{CDN}/ai/Qwen3-4B-Instruct-2507-Q4_K_M.gguf',
        sha256='',
        size=2_600_000_000,
        min_ram_gb=8,
        default_context=16_384,
        license='Apache 2.0',
        description='The default assistant for 8GB+ devices. A standout small tool-caller.',
    ),
]


def get_models_directory() -> Path:
    """Where GGUF model files are stored.  Always inside the media directory."""
    return get_media_directory() / 'ai/models'


async def fetch_models_manifest(url: str = None) -> dict:
    """Fetch the models manifest from the CDN and verify its GPG signature (map-manifest pattern)."""
    url = url or MODELS_MANIFEST_URL
    sig_url = f'{url}.sig'

    async with aiohttp_get(url, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f'Failed to fetch models manifest: HTTP {response.status}')
        manifest_bytes = await response.content.read()

    async with aiohttp_get(sig_url, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f'Failed to fetch models manifest signature: HTTP {response.status}')
        signature_bytes = await response.content.read()

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / 'models.json'
        sig_path = Path(tmpdir) / 'models.json.sig'
        manifest_path.write_bytes(manifest_bytes)
        sig_path.write_bytes(signature_bytes)

        if not await verify_gpg_signature(manifest_path, sig_path):
            raise RuntimeError('Models manifest GPG signature verification failed')

    logger.info('Models manifest GPG signature verified successfully')
    return json.loads(manifest_bytes)


async def get_models_catalog() -> (list, str):
    """The list of downloadable models, and where it came from ('cdn' or 'bundled').

    The CDN manifest wins when reachable; the bundled constant keeps the Manage tab working
    offline."""
    try:
        manifest = await fetch_models_manifest()
        models = manifest.get('models') or []
        if models:
            return models, 'cdn'
    except Exception as e:
        logger.debug(f'Could not fetch models manifest, using bundled catalog: {e}')
    return AI_MODELS, 'bundled'


def get_total_ram_bytes() -> int:
    return psutil.virtual_memory().total


def recommend_tier(total_ram_bytes: int = None) -> str:
    """Recommend a model tier for this device's RAM.  Other tiers stay selectable with a warning."""
    total_ram_bytes = total_ram_bytes if total_ram_bytes is not None else get_total_ram_bytes()
    gb = total_ram_bytes / 1024 ** 3
    if gb < 6:
        return 'small'
    if gb < 24:
        return 'medium'
    return 'large'
