"""Display backends: mock (PNG file) and Waveshare 2.7\" HAT (V1)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


class Display(Protocol):
    def show(self, image) -> None: ...
    def sleep(self) -> None: ...
    def close(self) -> None: ...


class MockDisplay:
    """Writes each frame to a PNG path for development without a HAT."""

    def __init__(self, path: str = "/tmp/wrolpi-epaper.png"):
        self.path = Path(path)
        self.frames = 0

    def show(self, image) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        image.save(self.path)
        self.frames += 1
        logger.info("Mock e-paper frame written to %s", self.path)

    def sleep(self) -> None:
        pass

    def close(self) -> None:
        pass


class HardwareDisplay:
    """
    Waveshare 2.7\" e-Paper HAT on Raspberry Pi (V1 driver).

    Pins (BCM): RST=17, DC=25, CS=8, BUSY=24, PWR=18, MOSI=10, SCLK=11.
    Landscape UI frames are 264×176; native panel buffer is 176×264.
    """

    def __init__(self):
        # Import from vendored package (relative imports inside epd2in7 → epdconfig).
        from controller.epaper.vendor import epd2in7

        self._epd_mod = epd2in7
        self._epd = epd2in7.EPD()
        self._initialized = False
        self._init()

    def _init(self) -> None:
        logger.info(
            "Initializing Waveshare 2.7\" (V1) %sx%s",
            self._epd.width,
            self._epd.height,
        )
        rc = self._epd.init()
        if rc != 0:
            raise RuntimeError(f"epd2in7.init() failed: {rc}")
        self._initialized = True

    def show(self, image) -> None:
        """
        Push a PIL image (ideally 264×176 landscape, mode '1' or convertible).
        Re-inits after sleep so consecutive frames work.
        """
        if not self._initialized:
            self._init()
        buf = self._epd.getbuffer(image)
        self._epd.display(buf)

    def sleep(self) -> None:
        if not self._initialized:
            return
        try:
            self._epd.sleep()
        except Exception as e:
            logger.warning("epd sleep failed: %s", e)
        self._initialized = False

    def close(self) -> None:
        try:
            self.sleep()
        except Exception:
            pass
        try:
            from controller.epaper.vendor import epdconfig

            epdconfig.module_exit()
        except Exception:
            pass


def open_display(mock: bool, mock_path: str) -> Display:
    if mock:
        return MockDisplay(mock_path)
    try:
        return HardwareDisplay()
    except Exception as e:
        logger.warning("Hardware e-paper unavailable (%s); falling back to mock", e)
        return MockDisplay(mock_path)
