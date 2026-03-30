import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

from modules.map import lib
from wrolpi.common import logger, verify_gpg_signature
from wrolpi.db import get_db_session
from wrolpi.downloader import Downloader, Download, DownloadResult, download_manager

__all__ = ['MapCatalogDownloader', 'MapExtractDownloader', 'map_catalog_downloader', 'map_extract_downloader']

logger = logger.getChild(__name__)

METALINK_NS = {'ml': 'urn:ietf:params:xml:ns:metalink'}


async def verify_meta4_signature(meta4_contents: bytes) -> bool:
    """Parse meta4 XML bytes, extract the hash and its GPG signature, and verify.

    Returns True if the signature is valid, False if invalid or missing."""
    try:
        root = ET.fromstring(meta4_contents)
        file_el = root.find('ml:file', METALINK_NS)
        if file_el is None:
            logger.warning('meta4 missing <file> element')
            return False

        hash_el = file_el.find('ml:hash[@type="sha-256"]', METALINK_NS)
        sig_el = file_el.find('ml:signature', METALINK_NS)

        if hash_el is None or hash_el.text is None:
            logger.warning('meta4 missing <hash type="sha-256"> element')
            return False
        if sig_el is None or sig_el.text is None:
            logger.warning('meta4 missing <signature> element — skipping verification')
            return False

        sha256_hash = hash_el.text.strip()
        signature = sig_el.text.strip()
    except ET.ParseError as e:
        logger.warning(f'Failed to parse meta4 XML: {e}')
        return False

    # Write hash and signature to temp files for GPG verification.
    with tempfile.TemporaryDirectory() as tmpdir:
        hash_path = Path(tmpdir) / 'hash'
        sig_path = Path(tmpdir) / 'hash.sig'
        hash_path.write_text(sha256_hash)
        sig_path.write_text(signature)

        return await verify_gpg_signature(hash_path, sig_path)


class MapCatalogDownloader(Downloader):
    """Fetches the manifest and creates a child Download for each subscribed region."""

    name = 'map_catalog'
    listable = False

    async def do_download(self, download: Download) -> DownloadResult:
        try:
            manifest = await lib.fetch_manifest(download.url)
        except Exception as e:
            logger.error(f'Failed to fetch map manifest: {e}')
            return DownloadResult(success=False, error=f'Failed to fetch manifest: {e}')

        version = manifest.get('version', '')
        manifest_regions = manifest.get('regions', {})

        if not manifest_regions:
            return DownloadResult(success=False, error='Manifest does not contain regions')

        regions = (download.settings or {}).get('regions', [])
        if not regions:
            return DownloadResult(success=True)

        created = 0
        with get_db_session(commit=True) as session:
            for r in regions:
                region = r.get('region', '')
                region_url = manifest_regions.get(region)
                if not region_url:
                    logger.warning(f'Subscribed region {region!r} not found in manifest — skipping')
                    continue

                # Delete stale download for this region if the URL changed (new version).
                old = session.query(Download).filter(
                    Download.downloader == 'map_extract',
                    Download.settings['region'].astext == region,
                    Download.url != region_url,
                ).one_or_none()
                if old:
                    logger.info(f'Deleting stale download for {region}: {old.url}')
                    session.delete(old)
                    session.flush()

                child = download_manager.get_or_create_download(session, region_url, reset_attempts=True,
                                                               override_skip=True)
                child.downloader = 'map_extract'
                child.location = '/map/manage'
                child.settings = {
                    'region': region,
                    'version': version,
                }
                child.renew(reset_attempts=True)
                created += 1

        if not created:
            return DownloadResult(success=False, error='No matching region URLs found in manifest')

        logger.info(f'Created {created} map region downloads')
        return DownloadResult(success=True, location='/map/manage')


map_catalog_downloader = MapCatalogDownloader()


class MapExtractDownloader(Downloader):
    """Downloads a pre-extracted region file from the CDN via aria2c.

    Settings contain: region, version — set by MapCatalogDownloader.

    Fetches the meta4 file once, GPG-verifies the hash signature, then passes
    the same meta4 bytes to aria2c for download hash verification. This ensures
    the hash that was GPG-verified is the same hash aria2c checks against.
    """

    name = 'map_extract'
    listable = False

    async def do_download(self, download: Download) -> DownloadResult:
        settings = download.settings or {}
        region = settings.get('region')
        version = settings.get('version', '')

        if not region:
            return DownloadResult(success=False, error='No region in download settings')

        map_directory = lib.get_map_directory()

        # Versioned filename.
        if version:
            output_name = f'{region}-{version}.pmtiles'
        else:
            output_name = f'{region}.pmtiles'
        output_path = map_directory / output_name
        tmp_path = map_directory / f'{output_name}.tmp'

        # Skip if versioned file already exists.
        if output_path.is_file():
            logger.info(f'{output_name} already exists, skipping download')
            return DownloadResult(success=True, location='/map')

        # Clean up any leftover temp file.
        if tmp_path.is_file():
            tmp_path.unlink()

        # Fetch meta4 once, GPG-verify the hash signature before downloading.
        meta4_contents = await self.get_meta4_contents(download.url)
        if meta4_contents:
            if not await verify_meta4_signature(meta4_contents):
                return DownloadResult(success=False,
                                     error=f'meta4 hash signature verification failed for {region}')
            logger.info(f'meta4 signature verified for {region}')
        else:
            logger.warning(f'No meta4 available for {region} — downloading without hash verification')

        # Download via aria2c, passing the pre-verified meta4 for hash checking.
        logger.warning(f'Downloading {region} from {download.url}')
        downloaded_path = None
        try:
            downloaded_path = await self.download_file(
                download, download.url, map_directory,
                check_for_meta4=False, concurrent=1, meta4_xml=meta4_contents,
            )
            downloaded_path.rename(tmp_path)
        except Exception as e:
            logger.error(f'Download failed for {region}: {e}')
            tmp_path.unlink(missing_ok=True)
            if downloaded_path:
                downloaded_path.unlink(missing_ok=True)
            return DownloadResult(success=False, error=f'Download failed: {str(e)[:500]}')

        if not tmp_path.is_file():
            return DownloadResult(success=False, error=f'Output file was not created: {tmp_path}')

        # Replace old file atomically.
        tmp_path.rename(output_path)

        # Delete older versions of this region.
        for old_file in map_directory.glob(f'{region}-*.pmtiles'):
            if old_file.name != output_name:
                logger.warning(f'Deleting old map version: {old_file}')
                old_file.unlink()
        # Also delete unversioned file if it exists.
        unversioned = map_directory / f'{region}.pmtiles'
        if unversioned.is_file() and unversioned.name != output_name:
            logger.warning(f'Deleting unversioned map file: {unversioned}')
            unversioned.unlink()

        size = output_path.stat().st_size
        logger.warning(f'Successfully downloaded {region} ({size} bytes) to {output_path}')

        return DownloadResult(success=True, location='/map')


map_extract_downloader = MapExtractDownloader()
