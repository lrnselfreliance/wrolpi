"""The tile service's HTTP server.

    GET /tiles/{z}/{x}/{y}.jpg   a 256 px tile
    GET /tiles/wrolpi.xml        the map source for ATAK and iTAK (MOBAC XML), with this server's address in it
    GET /tiles/status            what the service is doing (the map's ATAK tab shows it)

What ATAK does with a tile server (read from its source, `TileScraper` and `CustomMobacMapSource`), and what this
must do because of it:

- A downloader keeps whatever a tile request returns, whatever the response's headers say: a blank tile sent in
  place of one which was late would be a hole in the phone's map for good.  So a tile not drawn in time
  (`DEADLINE`, under ATAK's 5 seconds), or which failed, is a 503: ATAK tries each tile twice, and the second
  try finds the block drawn.  Only five tiles in a row failing both tries stop a download, and only a 401 or
  403 stops a map source; this sends neither.  Where there is no map, a tile is drawn of the background.
- The render processes are started with the service, not by the first tile: starting one is seconds.
- It asks for 4 tiles at a time (iTAK: 6), of the same block.  A block is drawn once however many ask for it.
- Phones are served in turn, a block of one then a block of the next, so one phone's download does not keep
  another's tiles waiting past the deadline.
"""
import asyncio
import collections
import logging
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from email.utils import formatdate
from pathlib import Path
from typing import Deque, Dict, Optional, Tuple
from xml.sax.saxutils import escape

from sanic import Sanic, response

from tiles import maps, render
from tiles.blocks import MAX_ZOOM, Block, block_of, is_tile
from tiles.cache import TileCache
from tiles.style import background_color, build_style, style_id

logger = logging.getLogger(__name__)

# ATAK gives up on a tile after 5 seconds; this leaves time for the tile to reach it.
DEADLINE = 4.0
# How long a phone keeps a tile.  ATAK keeps one at least a week whatever this says.
EXPIRES_SECONDS = 7 * 24 * 60 * 60
# Blocks a client may have waiting.  More is a phone which gave up on them; the oldest are dropped.
MAX_QUEUED_PER_CLIENT = 64
# How often the map directory is looked at for added, replaced and removed map files.
WATCH_SECONDS = 30
# Tiles per second is counted over this long.
RATE_SECONDS = 60
DEFAULT_MAX_ZOOM = 17
NAME = 'WROLPi Map'


def mobac_xml(base_url: str, name: str, max_zoom: int) -> str:
    """The MOBAC map source ATAK and iTAK import.  (No `backgroundColor`: ATAK reads only `#` and one digit.)"""
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<customMapSource>
    <name>{escape(name)}</name>
    <minZoom>0</minZoom>
    <maxZoom>{max_zoom}</maxZoom>
    <tileType>jpg</tileType>
    <tileUpdate>None</tileUpdate>
    <url>{escape(base_url)}/tiles/{{$z}}/{{$x}}/{{$y}}.jpg</url>
</customMapSource>
'''


class TileService:

    def __init__(self, map_directory: Path, cache: TileCache, processes: int = 2, max_zoom: int = DEFAULT_MAX_ZOOM,
                 overview: Optional[Path] = maps.OVERVIEW):
        self.map_directory = map_directory
        self.cache = cache
        self.processes = processes
        self.max_zoom = max_zoom
        self.overview = overview
        self.maps = []
        self.signature = None
        self.style: Optional[dict] = None
        self.style_id: Optional[str] = None
        self.blank_tile = b''
        self.executor: Optional[ProcessPoolExecutor] = None
        self.inflight: Dict[Tuple[str, Block], asyncio.Future] = dict()
        self.queues: 'collections.OrderedDict[str, Deque[Tuple[str, Block]]]' = collections.OrderedDict()
        self.condition: Optional[asyncio.Condition] = None
        self.tasks = []
        self.rendering = 0
        self.stats = collections.Counter()
        self.clients: Dict[str, dict] = dict()
        self.served = collections.deque()  # times tiles were served, for tiles per second

    # Map files and style.

    def refresh_maps(self) -> bool:
        """Draw with the map files now in the map directory.  Blocking.  True when they changed."""
        found = maps.find_maps(self.map_directory, self.overview)
        signature = maps.signature(found)
        if signature == self.signature:
            return False
        self.maps, self.signature = found, signature
        self.style = build_style(found)
        self.style_id = style_id(self.style, signature)
        self.blank_tile = render.blank(background_color(self.style))
        self.cache.use_style(self.style_id)
        logger.info(f'Drawing tiles of {len(found)} map files (style {self.style_id})')
        return True

    async def _watch(self):
        while True:
            await asyncio.sleep(WATCH_SECONDS)
            try:
                await asyncio.to_thread(self.refresh_maps)
            except Exception as e:
                logger.error('Failed to look for map files', exc_info=e)

    # Starting and stopping.

    def _new_executor(self) -> ProcessPoolExecutor:
        # spawn, not fork: a fork of this process would copy its event loop and threads.
        return ProcessPoolExecutor(max_workers=self.processes, mp_context=multiprocessing.get_context('spawn'),
                                   initializer=render.init_process)

    async def start(self):
        self.condition = asyncio.Condition()
        await asyncio.to_thread(self.refresh_maps)
        self.executor = self._new_executor()
        self.tasks = [asyncio.create_task(self._render_loop()) for _ in range(self.processes)]
        self.tasks.append(asyncio.create_task(self._watch()))
        self.tasks.append(asyncio.create_task(self._warm()))

    async def _warm(self):
        """Start every render process now, by drawing the world (zoom 0) in each, rather than when the first
        tiles are asked for."""
        loop = asyncio.get_running_loop()
        sid, style, block = self.style_id, self.style, Block(0, 0, 0)
        started = time.perf_counter()
        results = await asyncio.gather(
            *(loop.run_in_executor(self.executor, render.render_block, sid, style, block)
              for _ in range(self.processes)), return_exceptions=True)
        errors = [i for i in results if isinstance(i, BaseException)]
        if errors:
            logger.error('A render process could not draw', exc_info=errors[0])
            return
        await asyncio.to_thread(self.cache.put, block.z, results[0], sid)
        logger.info(f'{self.processes} render processes ready in {time.perf_counter() - started:.1f}s')

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        if self.executor:
            self.executor.shutdown(wait=False, cancel_futures=True)

    # Drawing.

    async def _next(self) -> Tuple[str, Block]:
        """The next block to draw: the oldest of the client whose turn it is."""
        async with self.condition:
            await self.condition.wait_for(lambda: bool(self.queues))
            client, queue = self.queues.popitem(last=False)
            item = queue.popleft()
            if queue:
                self.queues[client] = queue  # to the back of the line
            return item

    async def _render_loop(self):
        loop = asyncio.get_running_loop()
        while True:
            sid, block = await self._next()
            future = self.inflight.get((sid, block))
            if future is None or future.done():
                continue
            self.rendering += 1
            started = time.perf_counter()
            try:
                tiles = await loop.run_in_executor(self.executor, render.render_block, sid, self.style, block) \
                    if sid == self.style_id else None
            except BrokenProcessPool as e:
                # A render process died (the out-of-memory killer, most likely).  Start them again.
                logger.error('A render process died; starting new ones', exc_info=e)
                self.executor = self._new_executor()
                tiles, error = None, e
            except Exception as e:
                logger.error(f'Failed to draw block {block}', exc_info=e)
                tiles, error = None, e
            else:
                error = None
            finally:
                self.rendering -= 1
                self.inflight.pop((sid, block), None)
            if tiles:
                self.stats['blocks_drawn'] += 1
                self.stats['draw_ms'] += int((time.perf_counter() - started) * 1000)
                future.set_result(tiles)
                asyncio.create_task(asyncio.to_thread(self.cache.put, block.z, tiles, sid))
            elif error:
                self.stats['blocks_failed'] += 1
                future.set_exception(error)
            else:
                future.set_result(None)  # the map files changed while it waited

    async def _queue(self, client: str, sid: str, block: Block) -> asyncio.Future:
        future = asyncio.get_running_loop().create_future()
        self.inflight[(sid, block)] = future
        async with self.condition:
            queue = self.queues.setdefault(client, collections.deque())
            queue.append((sid, block))
            while len(queue) > MAX_QUEUED_PER_CLIENT:
                dropped = self.inflight.pop(queue.popleft(), None)
                if dropped and not dropped.done():
                    dropped.set_result(None)
                self.stats['blocks_dropped'] += 1
            self.condition.notify()
        return future

    async def tile(self, z: int, x: int, y: int, client: str) -> Tuple[Optional[bytes], bool]:
        """A tile, and whether it may be kept.  None when it was not drawn in time or could not be drawn: the
        phone must ask again (see the top of this module)."""
        self._seen(client)
        if not is_tile(z, x, y):
            self.stats['tiles_outside'] += 1
            return self.blank_tile, False
        sid = self.style_id
        data = await asyncio.to_thread(self.cache.get, z, x, y) if self.cache.enabled else None
        if data:
            self.stats['tiles_cached'] += 1
            return data, True

        block = block_of(z, x, y)
        future = self.inflight.get((sid, block))
        if future is None:
            future = await self._queue(client, sid, block)
        try:
            tiles = await asyncio.wait_for(asyncio.shield(future), DEADLINE)
        except asyncio.TimeoutError:
            self.stats['tiles_late'] += 1
            return None, False
        except Exception:
            self.stats['tiles_failed'] += 1
            return None, False
        if not tiles:
            self.stats['tiles_dropped'] += 1
            return None, False
        self.stats['tiles_drawn'] += 1
        return tiles[(x, y)], True

    def _seen(self, client: str):
        now = time.time()
        entry = self.clients.setdefault(client, dict(tiles=0, first_seen=now))
        entry['tiles'] += 1
        entry['last_seen'] = now
        self.served.append(now)

    def status(self) -> dict:
        now = time.time()
        while self.served and self.served[0] < now - RATE_SECONDS:
            self.served.popleft()
        for client in [k for k, v in self.clients.items() if v['last_seen'] < now - 24 * 60 * 60]:
            del self.clients[client]
        drawn = self.stats['blocks_drawn']
        return dict(
            renderer=render.available(),
            processes=self.processes,
            max_zoom=self.max_zoom,
            maps=[str(i) for i in self.maps],
            style_id=self.style_id,
            queued_blocks=sum(len(i) for i in self.queues.values()),
            drawing_blocks=self.rendering,
            tiles_per_second=round(len(self.served) / RATE_SECONDS, 1),
            block_ms=round(self.stats['draw_ms'] / drawn) if drawn else None,
            cache=dict(enabled=self.cache.enabled, bytes=self.cache.size, max_bytes=self.cache.max_bytes),
            stats=dict(self.stats),
            clients=[dict(client=k, tiles=v['tiles'], first_seen=round(v['first_seen']),
                          last_seen=round(v['last_seen']),
                          queued_blocks=len(self.queues.get(k, ())))
                     for k, v in sorted(self.clients.items(), key=lambda i: -i[1]['last_seen'])],
        )


def client_of(request) -> str:
    """The phone asking: Caddy puts its address first in X-Forwarded-For."""
    forwarded = request.headers.get('x-forwarded-for')
    return forwarded.split(',')[0].strip() if forwarded else request.ip


def base_url_of(request) -> str:
    """The address the phone reached this server by, as Caddy says (the LAN, the hotspot, or a name)."""
    scheme = request.headers.get('x-forwarded-proto') or request.scheme
    host = request.headers.get('x-forwarded-host') or request.headers.get('host') or request.host
    return f'{scheme}://{host}'


def create_app(service: TileService, name: str = 'wrolpi_tiles') -> Sanic:
    app = Sanic(name)
    # sanic-ext (installed for the API) would add OpenAPI docs and more, for nothing: seconds of startup on a Pi.
    app.config.AUTO_EXTEND = False
    app.ctx.service = service

    @app.before_server_start
    async def start(app_):
        await app_.ctx.service.start()

    @app.after_server_stop
    async def stop(app_):
        await app_.ctx.service.stop()

    @app.get('/tiles/<z:int>/<x:int>/<name:str>')
    async def get_tile(request, z: int, x: int, name: str):
        y, _, suffix = name.partition('.')
        if suffix != 'jpg' or not y.isdigit():
            return response.text('not found', status=404)
        data, keep = await app.ctx.service.tile(z, x, int(y), client_of(request))
        if data is None:
            # Not a 401 or 403: those stop an ATAK map source.
            return response.text('Not drawn yet, try again', status=503,
                                 headers={'Retry-After': '1', 'Cache-Control': 'no-store'})
        if keep:
            headers = {'Cache-Control': f'max-age={EXPIRES_SECONDS}',
                       'Expires': formatdate(time.time() + EXPIRES_SECONDS, usegmt=True)}
        else:
            headers = {'Cache-Control': 'no-store', 'Expires': formatdate(0, usegmt=True)}
        return response.raw(data, content_type=render.CONTENT_TYPE, headers=headers)

    @app.get('/tiles/wrolpi.xml')
    async def get_xml(request):
        base_url = base_url_of(request)
        https = base_url.startswith('https:')
        name = f'{NAME} (HTTPS)' if https else NAME
        filename = 'wrolpi-map-https.xml' if https else 'wrolpi-map.xml'
        return response.text(mobac_xml(base_url, name, app.ctx.service.max_zoom), content_type='application/xml',
                             headers={'Content-Disposition': f'attachment; filename="{filename}"'})

    @app.get('/tiles/status')
    async def get_status(request):
        return response.json(app.ctx.service.status())

    return app
