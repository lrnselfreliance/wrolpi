"""The AI model catalog.

The bundled AI_MODELS constant is the offline fallback (like the map module's MAP_REGIONS);
the CDN manifest at ai/models.json is fetched at browse/download time and GPG-verified with the
committed WROLPi public key.  The release process refreshes AI_MODELS from the published manifest.
"""
import json
import tempfile
import time
from pathlib import Path
from typing import Optional

import psutil

from wrolpi import flags
from wrolpi.common import aiohttp_get, get_media_directory, logger, verify_gpg_signature

logger = logger.getChild(__name__)

CDN = 'https://wrolpi.nyc3.cdn.digitaloceanspaces.com'
MODELS_MANIFEST_URL = f'{CDN}/ai/models.json'
# The manifest is ~2KB; a black-holed network must not cost 30s per Manage-page poll.
MANIFEST_TIMEOUT = 5
# How long a fetched (or failed) manifest is reused before the CDN is asked again.
MANIFEST_CACHE_SECONDS = 60 * 60

# Sizes are bytes; sha256 values match the published manifest (wrolpi/scripts/publish_ai_models.py
# refreshes both).  The meta4 sidecar (GPG-verified at download time) is what enforces the hash.
AI_MODELS = [
    dict(
        name='Qwen3-1.7B-Q4_K_M.gguf',
        tier='small',
        url=f'{CDN}/ai/Qwen3-1.7B-Q4_K_M.gguf',
        sha256='b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897',
        size=1_107_409_472,
        min_ram_gb=4,
        default_context=8_192,
        license='Apache 2.0',
        description='The default assistant for 4GB devices (Pi 4/5). Best tool-calling per byte.',
    ),
    dict(
        name='Qwen3-4B-Instruct-2507-Q4_K_M.gguf',
        tier='medium',
        url=f'{CDN}/ai/Qwen3-4B-Instruct-2507-Q4_K_M.gguf',
        sha256='3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597',
        size=2_497_281_120,
        min_ram_gb=8,
        default_context=16_384,
        license='Apache 2.0',
        description='The default assistant for 8GB+ devices. A standout small tool-caller.',
    ),
]


def get_models_directory() -> Path:
    """Where GGUF model files are stored.  Always inside the media directory."""
    return get_media_directory() / 'ai/models'


# Printable ASCII only, minus the characters the shell config reader cannot round-trip.
# start_llama_server.sh reads active_model back out of ai.yaml with read_config_value.sh: PyYAML
# escapes non-ASCII (\xE9), the reader strips " #..." before unquoting, and quotes/backslashes
# survive as literal characters.  The start script's traversal guard also rejects any ".." run.
_UNLOADABLE_CHARS = set('#"\'\\/')


def is_loadable_model_name(name: str) -> bool:
    """True when llama-server can be started with this file name from ai/models.

    Catalog names always pass; this exists for GGUFs the user copies in by hand."""
    if not name or not name.endswith('.gguf') or name != name.strip():
        return False
    if '..' in name or any(c in _UNLOADABLE_CHARS for c in name):
        return False
    return all(0x20 <= ord(c) < 0x7F for c in name)


async def fetch_models_manifest(url: str = None) -> dict:
    """Fetch the models manifest from the CDN and verify its GPG signature (map-manifest pattern)."""
    url = url or MODELS_MANIFEST_URL
    sig_url = f'{url}.sig'

    async with aiohttp_get(url, timeout=MANIFEST_TIMEOUT) as response:
        if response.status != 200:
            raise RuntimeError(f'Failed to fetch models manifest: HTTP {response.status}')
        manifest_bytes = await response.content.read()

    async with aiohttp_get(sig_url, timeout=MANIFEST_TIMEOUT) as response:
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


# (models, source, expires_at) from the last CDN attempt, success or failure.  Per process.
_catalog_cache: Optional[tuple[list, str, float]] = None


def clear_models_catalog_cache():
    global _catalog_cache
    _catalog_cache = None


async def get_models_catalog() -> (list, str):
    """The list of downloadable models, and where it came from ('cdn' or 'bundled').

    The CDN manifest wins when reachable; the bundled constant keeps the Manage tab working
    offline.  The CDN is not tried while the have_internet flag is clear, and the result of an
    attempt (including a failure) is reused for MANIFEST_CACHE_SECONDS so the Manage tab's 30s
    polling does not pay the fetch on every request."""
    global _catalog_cache
    if _catalog_cache and _catalog_cache[2] > time.monotonic():
        return _catalog_cache[0], _catalog_cache[1]

    # `is_set()` is None under pytest without the flags lock: only an explicit False skips.
    if flags.have_internet.is_set() is False:
        logger.debug('No internet, using bundled models catalog')
        return AI_MODELS, 'bundled'

    models, source = AI_MODELS, 'bundled'
    try:
        manifest = await fetch_models_manifest()
        if cdn_models := manifest.get('models'):
            models, source = cdn_models, 'cdn'
    except Exception as e:
        logger.debug(f'Could not fetch models manifest, using bundled catalog: {e}')
    _catalog_cache = (models, source, time.monotonic() + MANIFEST_CACHE_SECONDS)
    return models, source


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


def get_model_default_context(name: str) -> Optional[int]:
    """The bundled catalog's default context size for a model, if known."""
    for model in AI_MODELS:
        if model['name'] == name:
            return model.get('default_context')
    return None


def get_effective_context_size() -> int:
    """The context llama-server runs with: the explicit ai.yaml value, else the active model's
    catalog default, else the conservative small-tier default.  start_llama_server.sh reads the
    explicit value; manage_settings writes the model default there on model selection so the
    script and this function agree."""
    from modules.ai.config import get_ai_config
    config = get_ai_config()
    return config.context_size or get_model_default_context(config.active_model) or 8_192
