import pathlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from modules.map import lib
from wrolpi.common import logger, verify_gpg_signature
from wrolpi.downloader import (
    Download,
    DownloadContext,
    Downloader,
    DownloadResult,
    download_manager,
)

__all__ = [
    'MapCatalogDownloader', 'MapExtractDownloader', 'MapSearchIndexDownloader',
    'PreparedMapCatalog', 'ExecutedMapCatalog',
    'PreparedMapExtract', 'ExecutedMapExtract',
    'PreparedMapSearchIndex', 'ExecutedMapSearchIndex',
    'map_catalog_downloader', 'map_extract_downloader', 'map_search_index_downloader',
]

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


# ---------------------------------------------------------------------------
# MapCatalogDownloader
# ---------------------------------------------------------------------------


@dataclass
class PreparedMapCatalog:
    """Plan produced by MapCatalogDownloader.prepare_download.

    `subscribed_regions` is the list of {region: ...} dicts the user has chosen to track.
    The manifest itself is fetched in execute_download.
    """
    url: str
    subscribed_regions: List[dict]


@dataclass
class ExecutedMapCatalog:
    """Output of MapCatalogDownloader.execute_download.

    Either `manifest` is populated (success) or `error` is set (fetch failed).  Child
    download creation happens in finalize_download where the manager's session is in
    scope.
    """
    manifest: Optional[dict]
    subscribed_regions: List[dict]
    error: Optional[str] = None


class MapCatalogDownloader(Downloader):
    """Fetches the manifest and creates a child Download for each subscribed region."""

    name = 'map_catalog'
    listable = False

    def prepare_download(self, session: Session, download: Download) -> PreparedMapCatalog:
        subscribed = (download.settings or {}).get('regions', [])
        return PreparedMapCatalog(url=download.url, subscribed_regions=subscribed)

    async def execute_download(self, prepared: PreparedMapCatalog, ctx: DownloadContext,
                               download: Download = None) -> ExecutedMapCatalog:
        try:
            manifest = await lib.fetch_manifest(prepared.url)
        except Exception as e:
            logger.error(f'Failed to fetch map manifest: {e}')
            return ExecutedMapCatalog(
                manifest=None,
                subscribed_regions=prepared.subscribed_regions,
                error=f'Failed to fetch manifest: {e}',
            )
        return ExecutedMapCatalog(manifest=manifest,
                                  subscribed_regions=prepared.subscribed_regions)

    def finalize_download(self, session: Session, download: Download,
                          executed: ExecutedMapCatalog) -> DownloadResult:
        if executed.error:
            return DownloadResult(success=False, error=executed.error)

        manifest = executed.manifest or {}
        version = manifest.get('version', '')
        manifest_regions = manifest.get('regions', {})
        search_indexes = manifest.get('search_indexes', {})

        if not manifest_regions:
            return DownloadResult(success=False, error='Manifest does not contain regions')

        if not executed.subscribed_regions:
            return DownloadResult(success=True)

        map_directory = lib.get_map_directory()

        created = 0
        # Defer search-index downloads so they are all inserted AFTER every pmtiles
        # download. Downloads process in insertion order; this prevents a search-index
        # download from running before its companion pmtiles file exists on disk.
        pending_search_downloads = []
        for r in executed.subscribed_regions:
            region = r.get('region', '')
            region_url = manifest_regions.get(region)
            if not region_url:
                logger.warning(f'Subscribed region {region!r} not found in manifest — skipping')
                continue

            # Compute the expected PMTiles filename.
            if version:
                pmtiles_name = f'{region}-{version}.pmtiles'
            else:
                pmtiles_name = f'{region}.pmtiles'

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
                'search_index_url': search_indexes.get(region, ''),
            }
            child.renew(reset_attempts=True)
            created += 1

            # Queue search index download if the CDN provides one and the
            # .search.db file does not already exist on disk.
            search_url = search_indexes.get(region)
            search_db_path = (map_directory / pmtiles_name).with_suffix('.search.db')
            if search_url and not search_db_path.is_file():
                pending_search_downloads.append((region, search_url, pmtiles_name))

        # Insert all search-index downloads after every pmtiles download, so they
        # process in insertion order behind their companion pmtiles.
        for region, search_url, pmtiles_name in pending_search_downloads:
            search_child = download_manager.get_or_create_download(
                session, search_url, reset_attempts=True, override_skip=True)
            search_child.downloader = 'map_search_index'
            search_child.location = '/map/manage'
            search_child.settings = {'region': region, 'pmtiles_name': pmtiles_name}
            search_child.renew(reset_attempts=True)
            logger.info(f'Created search index download for {region}')

        if not created:
            return DownloadResult(success=False, error='No matching region URLs found in manifest')

        logger.info(f'Created {created} map region downloads')

        return DownloadResult(success=True, location='/map/manage')


map_catalog_downloader = MapCatalogDownloader()


# ---------------------------------------------------------------------------
# MapExtractDownloader
# ---------------------------------------------------------------------------


@dataclass
class PreparedMapExtract:
    """Plan produced by MapExtractDownloader.prepare_download.

    Filenames are computed from settings; `already_done` short-circuits execute when
    the output already exists.  `error` carries an early validation failure (e.g. no
    region in settings).
    """
    region: str
    version: str
    map_directory: pathlib.Path
    output_name: str
    output_path: pathlib.Path
    tmp_path: pathlib.Path
    already_done: bool = False
    error: Optional[str] = None


@dataclass
class ExecutedMapExtract:
    """Output of MapExtractDownloader.execute_download.

    `skipped` covers the already-done short-circuit; `error` covers download/verify
    failures.  Otherwise the file is at output_path and finalize decides whether to
    rebuild the search index locally.
    """
    region: str
    output_path: pathlib.Path
    map_directory: pathlib.Path
    skipped: bool = False
    error: Optional[str] = None


class MapExtractDownloader(Downloader):
    """Downloads a pre-extracted region file from the CDN via aria2c.

    Settings contain: region, version — set by MapCatalogDownloader.

    Fetches the meta4 file once, GPG-verifies the hash signature, then passes
    the same meta4 bytes to aria2c for download hash verification. This ensures
    the hash that was GPG-verified is the same hash aria2c checks against.
    """

    name = 'map_extract'
    listable = False

    def prepare_download(self, session: Session, download: Download) -> PreparedMapExtract:
        settings = download.settings or {}
        region = settings.get('region')
        version = settings.get('version', '')

        if not region:
            return PreparedMapExtract(
                region='', version='', map_directory=pathlib.Path('.'),
                output_name='', output_path=pathlib.Path('.'), tmp_path=pathlib.Path('.'),
                error='No region in download settings',
            )

        map_directory = lib.get_map_directory()
        # Versioned filename.
        if version:
            output_name = f'{region}-{version}.pmtiles'
        else:
            output_name = f'{region}.pmtiles'
        output_path = map_directory / output_name
        tmp_path = map_directory / f'{output_name}.tmp'

        prepared = PreparedMapExtract(
            region=region, version=version, map_directory=map_directory,
            output_name=output_name, output_path=output_path, tmp_path=tmp_path,
        )

        # Skip if versioned file already exists.
        if output_path.is_file():
            logger.info(f'{output_name} already exists, skipping download')
            prepared.already_done = True
            return prepared

        # Clean up any leftover temp file.
        if tmp_path.is_file():
            tmp_path.unlink()

        return prepared

    async def execute_download(self, prepared: PreparedMapExtract, ctx: DownloadContext,
                               download: Download = None) -> ExecutedMapExtract:
        if prepared.error:
            return ExecutedMapExtract(region=prepared.region, output_path=prepared.output_path,
                                      map_directory=prepared.map_directory, error=prepared.error)
        if prepared.already_done:
            return ExecutedMapExtract(region=prepared.region, output_path=prepared.output_path,
                                      map_directory=prepared.map_directory, skipped=True)

        download = download if download is not None else Download(url=prepared.output_path.name)
        # The original download URL is needed for download_file; the manager passes the real
        # Download in production, so we read .url from it.  In unit tests, callers must supply
        # `download` with a URL.
        url = download.url

        # Fetch meta4 once, GPG-verify the hash signature before downloading.
        meta4_contents = await self.get_meta4_contents(url)
        if meta4_contents:
            if not await verify_meta4_signature(meta4_contents):
                return ExecutedMapExtract(
                    region=prepared.region, output_path=prepared.output_path,
                    map_directory=prepared.map_directory,
                    error=f'meta4 hash signature verification failed for {prepared.region}',
                )
            logger.info(f'meta4 signature verified for {prepared.region}')
        else:
            logger.warning(f'No meta4 available for {prepared.region} — downloading without hash verification')

        # Download via aria2c, passing the pre-verified meta4 for hash checking.
        logger.warning(f'Downloading {prepared.region} from {url}')
        downloaded_path = None
        try:
            downloaded_path = await self.download_file(
                download, url, prepared.map_directory,
                check_for_meta4=False, concurrent=1, meta4_xml=meta4_contents,
                ctx=ctx,
            )
            downloaded_path.rename(prepared.tmp_path)
        except Exception as e:
            logger.error(f'Download failed for {prepared.region}: {e}')
            prepared.tmp_path.unlink(missing_ok=True)
            if downloaded_path:
                downloaded_path.unlink(missing_ok=True)
            return ExecutedMapExtract(
                region=prepared.region, output_path=prepared.output_path,
                map_directory=prepared.map_directory,
                error=f'Download failed: {str(e)[:500]}',
            )

        if not prepared.tmp_path.is_file():
            return ExecutedMapExtract(
                region=prepared.region, output_path=prepared.output_path,
                map_directory=prepared.map_directory,
                error=f'Output file was not created: {prepared.tmp_path}',
            )

        # Replace old file atomically.
        prepared.tmp_path.rename(prepared.output_path)

        # Delete older versions of this region.
        for old_file in prepared.map_directory.glob(f'{prepared.region}-*.pmtiles'):
            if old_file.name != prepared.output_name:
                logger.warning(f'Deleting old map version: {old_file}')
                old_file.unlink()
        # Also delete unversioned file if it exists.
        unversioned = prepared.map_directory / f'{prepared.region}.pmtiles'
        if unversioned.is_file() and unversioned.name != prepared.output_name:
            logger.warning(f'Deleting unversioned map file: {unversioned}')
            unversioned.unlink()

        size = prepared.output_path.stat().st_size
        logger.warning(f'Successfully downloaded {prepared.region} ({size} bytes) to {prepared.output_path}')

        return ExecutedMapExtract(region=prepared.region, output_path=prepared.output_path,
                                  map_directory=prepared.map_directory)

    def finalize_download(self, session: Session, download: Download,
                          executed: ExecutedMapExtract) -> DownloadResult:
        if executed.error:
            return DownloadResult(success=False, error=executed.error)
        if executed.skipped:
            return DownloadResult(success=True, location='/map')

        # Build search index locally if tippecanoe is available and no CDN
        # search index download already exists for this region.
        has_search_download = session.query(Download).filter(
            Download.downloader == 'map_search_index',
            Download.settings['region'].astext == executed.region,
        ).count() > 0
        if not has_search_download:
            try:
                from modules.map.search import rebuild_search_index
                rebuild_search_index(executed.output_path.name)
            except Exception as e:
                logger.error(f'Failed to start search index build for {executed.region}: {e}')

        return DownloadResult(success=True, location='/map')


map_extract_downloader = MapExtractDownloader()


# ---------------------------------------------------------------------------
# MapSearchIndexDownloader
# ---------------------------------------------------------------------------


@dataclass
class PreparedMapSearchIndex:
    """Plan produced by MapSearchIndexDownloader.prepare_download.

    `error` covers missing settings or a missing PMTiles file (the search index can't
    exist without one).  `already_done` short-circuits when the .search.db is on disk.
    """
    region: str
    pmtiles_name: str
    map_directory: pathlib.Path
    pmtiles_path: pathlib.Path
    search_db_path: pathlib.Path
    already_done: bool = False
    error: Optional[str] = None


@dataclass
class ExecutedMapSearchIndex:
    region: str
    skipped: bool = False
    error: Optional[str] = None


class MapSearchIndexDownloader(Downloader):
    """Downloads a pre-built .search.db file from the CDN via aria2c with meta4 verification.

    Created by MapCatalogDownloader alongside map_extract downloads for each
    subscribed region.  Will wait (fail + retry) until the PMTiles file exists.
    """

    name = 'map_search_index'
    listable = False

    def prepare_download(self, session: Session, download: Download) -> PreparedMapSearchIndex:
        settings = download.settings or {}
        region = settings.get('region', '')
        pmtiles_name = settings.get('pmtiles_name', '')

        map_directory = lib.get_map_directory()

        prepared = PreparedMapSearchIndex(
            region=region, pmtiles_name=pmtiles_name, map_directory=map_directory,
            pmtiles_path=map_directory / pmtiles_name if pmtiles_name else map_directory,
            search_db_path=(map_directory / pmtiles_name).with_suffix('.search.db')
            if pmtiles_name else map_directory,
        )

        if not region or not pmtiles_name:
            prepared.error = 'Missing region or pmtiles_name in settings'
            return prepared

        if not prepared.pmtiles_path.is_file():
            prepared.error = f'PMTiles file not found: {pmtiles_name}'
            return prepared

        if prepared.search_db_path.is_file():
            logger.info(f'Search index already exists for {region}, skipping')
            prepared.already_done = True

        return prepared

    async def execute_download(self, prepared: PreparedMapSearchIndex, ctx: DownloadContext,
                               download: Download = None) -> ExecutedMapSearchIndex:
        if prepared.error:
            return ExecutedMapSearchIndex(region=prepared.region, error=prepared.error)
        if prepared.already_done:
            return ExecutedMapSearchIndex(region=prepared.region, skipped=True)

        download = download if download is not None else Download(url=prepared.pmtiles_name)
        url = download.url

        # Fetch and verify meta4 (GPG-signed hash).
        meta4_contents = await self.get_meta4_contents(url)
        if meta4_contents:
            if not await verify_meta4_signature(meta4_contents):
                return ExecutedMapSearchIndex(
                    region=prepared.region,
                    error=f'meta4 signature verification failed for {prepared.region} search index',
                )
            logger.info(f'Search index meta4 verified for {prepared.region}')

        # Download via aria2c with meta4 hash verification.
        logger.warning(f'Downloading search index for {prepared.region} from {url}')
        downloaded_path = None
        try:
            downloaded_path = await self.download_file(
                download, url, prepared.map_directory,
                check_for_meta4=False, concurrent=1, meta4_xml=meta4_contents,
                ctx=ctx,
            )
            # Rename to match the local PMTiles filename.
            downloaded_path.rename(prepared.search_db_path)
        except Exception as e:
            logger.error(f'Search index download failed for {prepared.region}: {e}')
            if downloaded_path:
                downloaded_path.unlink(missing_ok=True)
            prepared.search_db_path.unlink(missing_ok=True)
            return ExecutedMapSearchIndex(
                region=prepared.region,
                error=f'Download failed: {str(e)[:500]}',
            )

        size = prepared.search_db_path.stat().st_size
        logger.warning(f'Downloaded search index for {prepared.region} ({size} bytes)')
        return ExecutedMapSearchIndex(region=prepared.region)

    def finalize_download(self, session: Session, download: Download,
                          executed: ExecutedMapSearchIndex) -> DownloadResult:
        if executed.error:
            return DownloadResult(success=False, error=executed.error)
        return DownloadResult(success=True, location='/map')


map_search_index_downloader = MapSearchIndexDownloader()
