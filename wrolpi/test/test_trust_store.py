"""
Tests that WROLPi's TLS clients do not trust compromised certificate authorities.
"""
import certifi
import pytest

from wrolpi.vars import PROJECT_DIR

# Roots of the eMudhra intermediates whose private keys can be recovered from their certificates.
DISTRUSTED_ROOT_LABELS = (
    'emSign ECC Root CA - G3',
)


@pytest.mark.parametrize('label', DISTRUSTED_ROOT_LABELS)
def test_certifi_distrusts_root(label):
    """certifi's bundle (used by yt-dlp, requests and curl-cffi) must not contain a distrusted root."""
    labels = [line.split('"')[1] for line in certifi.contents().splitlines() if line.startswith('# Label: "')]
    assert labels, 'certifi bundle has no labels; cannot verify distrusted roots are absent'
    assert label not in labels


@pytest.mark.parametrize('path,setting', [
    ('etc/raspberrypios/wrolpi-api.service', 'Environment=DENO_TLS_CA_STORE=system'),
    ('etc/raspberrypios/wrolpi-api-dev.service', 'Environment=DENO_TLS_CA_STORE=system'),
    ('docker/api/Dockerfile', 'ENV DENO_TLS_CA_STORE=system'),
    ('docker/archive/Dockerfile', 'ENV DENO_TLS_CA_STORE=system'),
])
def test_deno_uses_system_trust_store(path, setting):
    """Deno's bundled roots only change with a Deno upgrade; the system store is patched by apt."""
    assert setting in (PROJECT_DIR / path).read_text().splitlines()
