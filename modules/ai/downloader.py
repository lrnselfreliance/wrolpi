"""Downloads GGUF model files from the WROLPi CDN into <media>/ai/models/.

Follows the map-extract pattern: the per-file .meta4 sidecar is fetched once and its hash
signature GPG-verified, then the same bytes are handed to aria2c so the hash that was verified
is the hash that is enforced.  Downloads are resumable and respect the media_mounted rules via
the download manager."""
import pathlib
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from modules.ai.catalog import get_models_directory
from modules.map.downloader import verify_meta4_signature
from wrolpi.common import logger
from wrolpi.downloader import Download, DownloadContext, Downloader, DownloadResult
from wrolpi.events import Events

__all__ = ['ModelDownloader', 'PreparedModel', 'ExecutedModel', 'ai_model_downloader']

logger = logger.getChild(__name__)


@dataclass
class PreparedModel:
    """Plan produced by ModelDownloader.prepare_download."""
    name: str
    models_directory: pathlib.Path
    output_path: pathlib.Path
    tmp_path: pathlib.Path
    already_done: bool = False
    error: Optional[str] = None


@dataclass
class ExecutedModel:
    """Output of ModelDownloader.execute_download."""
    name: str
    output_path: pathlib.Path
    skipped: bool = False
    error: Optional[str] = None


class ModelDownloader(Downloader):
    """Downloads one GGUF model file via aria2c with GPG-verified hash checking."""

    name = 'ai_model'
    listable = False

    def prepare_download(self, session: Session, download: Download) -> PreparedModel:
        name = download.url.rstrip('/').rsplit('/', 1)[-1]
        models_directory = get_models_directory()
        output_path = models_directory / name
        tmp_path = models_directory / f'{name}.tmp'

        if not name.endswith('.gguf'):
            return PreparedModel(name=name, models_directory=models_directory, output_path=output_path,
                                 tmp_path=tmp_path, error=f'Not a GGUF model URL: {download.url}')

        prepared = PreparedModel(name=name, models_directory=models_directory, output_path=output_path,
                                 tmp_path=tmp_path)
        if output_path.is_file():
            logger.info(f'{name} already exists, skipping download')
            prepared.already_done = True
            return prepared

        models_directory.mkdir(parents=True, exist_ok=True)
        # Clean up any leftover temp file; aria2c resumes its own .aria2 checkpoints.
        tmp_path.unlink(missing_ok=True)
        return prepared

    async def execute_download(self, prepared: PreparedModel, ctx: DownloadContext,
                               download: Download = None) -> ExecutedModel:
        if prepared.error:
            return ExecutedModel(name=prepared.name, output_path=prepared.output_path, error=prepared.error)
        if prepared.already_done:
            return ExecutedModel(name=prepared.name, output_path=prepared.output_path, skipped=True)

        url = download.url

        # Fetch the meta4 once, GPG-verify the hash signature before downloading.
        meta4_contents = await self.get_meta4_contents(url)
        if not meta4_contents:
            return ExecutedModel(name=prepared.name, output_path=prepared.output_path,
                                 error=f'No meta4 available for {prepared.name}; refusing an unverified download')
        if not await verify_meta4_signature(meta4_contents):
            return ExecutedModel(name=prepared.name, output_path=prepared.output_path,
                                 error=f'meta4 hash signature verification failed for {prepared.name}')
        logger.info(f'meta4 signature verified for {prepared.name}')

        downloaded_path = None
        try:
            downloaded_path = await self.download_file(
                download, url, prepared.models_directory,
                check_for_meta4=False, concurrent=1, meta4_xml=meta4_contents,
                ctx=ctx,
            )
            downloaded_path.rename(prepared.tmp_path)
        except Exception as e:
            logger.error(f'Model download failed for {prepared.name}: {e}')
            prepared.tmp_path.unlink(missing_ok=True)
            if downloaded_path:
                downloaded_path.unlink(missing_ok=True)
            return ExecutedModel(name=prepared.name, output_path=prepared.output_path,
                                 error=f'Download failed: {str(e)[:500]}')

        # Replace atomically.
        prepared.tmp_path.rename(prepared.output_path)
        return ExecutedModel(name=prepared.name, output_path=prepared.output_path)

    def finalize_download(self, session: Session, download: Download, executed: ExecutedModel) -> DownloadResult:
        if executed.error:
            return DownloadResult(success=False, error=executed.error)
        if not executed.skipped:
            Events.send_user_notify(f'AI model downloaded: {executed.name}', url='/ai/manage')
        return DownloadResult(success=True, location='/ai/manage')


# Instantiating registers with the download manager.
ai_model_downloader = ModelDownloader()
