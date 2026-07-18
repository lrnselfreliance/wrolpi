#!/usr/bin/env python3
"""
Drive a Waveshare 2.7\" e-Paper (V2, 176×264 native) via Flipper FlipTDI (FT232H).

Requires FlipTDI open on the Flipper so USB shows as 0403:6014.

Wiring (FlipTDI / FT232H ADBUS → Waveshare SPI):
  ADBUS0 / Flipper A7  → CLK
  ADBUS1 / Flipper A6  → DIN (MOSI)
  ADBUS2 / Flipper A4  → (MISO unused)
  ADBUS3 / Flipper B3  → CS
  ADBUS4 / Flipper B2  → DC
  ADBUS5 / Flipper C3  → RST
  ADBUS6 / Flipper C1  → BUSY
  3V3 / GND as needed

Usage:
  python3 -m controller.epaper.fliptdi_epd27 clear
  python3 -m controller.epaper.fliptdi_epd27 image path/to.png
  python3 -m controller.epaper.fliptdi_epd27 demo
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("fliptdi_epd27")

# Native panel orientation in Waveshare driver (portrait).
EPD_WIDTH = 176
EPD_HEIGHT = 264

# ADBUS bit masks (SPI owns 0–3; we use 4–6 for control).
PIN_DC = 1 << 4
PIN_RST = 1 << 5
PIN_BUSY = 1 << 6

DEFAULT_URL = "ftdi://ftdi:232h:1:f/1"
# Fallback if auto URL differs
FALLBACK_URLS = (
    "ftdi://ftdi:232h:1:f/1",
    "ftdi://ftdi:232h/1",
    "ftdi://0403:6014/1",
)


class FlipTdiEpd27:
    def __init__(self, url: Optional[str] = None, spi_hz: float = 2_000_000):
        from pyftdi.spi import SpiController

        self._spi_ctrl = SpiController(cs_count=1)
        last_err = None
        urls = [url] if url else list(FALLBACK_URLS)
        for u in urls:
            if not u:
                continue
            try:
                self._spi_ctrl.configure(u)
                self.url = u
                logger.info("Opened %s", u)
                break
            except Exception as e:
                last_err = e
                try:
                    self._spi_ctrl.close()
                except Exception:
                    pass
                self._spi_ctrl = SpiController(cs_count=1)
        else:
            raise RuntimeError(f"Could not open FlipTDI: {last_err}")

        self._port = self._spi_ctrl.get_port(cs=0, freq=spi_hz, mode=0)
        self._gpio = self._spi_ctrl.get_gpio()
        # DC+RST outputs, BUSY input
        self._gpio.set_direction(PIN_DC | PIN_RST | PIN_BUSY, PIN_DC | PIN_RST)
        self._gpio.write(PIN_DC | PIN_RST)  # idle high
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT

    def close(self) -> None:
        try:
            self._spi_ctrl.close()
        except Exception:
            pass

    def _write_gpio(self, high_mask: int) -> None:
        """Set DC/RST levels; other output bits left as given mask (BUSY ignored)."""
        self._gpio.write(high_mask & (PIN_DC | PIN_RST))

    def reset(self) -> None:
        self._write_gpio(PIN_DC | PIN_RST)
        time.sleep(0.05)
        self._write_gpio(PIN_DC)  # RST low
        time.sleep(0.01)
        self._write_gpio(PIN_DC | PIN_RST)
        time.sleep(0.05)

    def _cmd(self, command: int) -> None:
        self._write_gpio(PIN_RST)  # DC=0, RST=1
        self._port.write(bytes([command & 0xFF]))

    def _data(self, data: int) -> None:
        self._write_gpio(PIN_DC | PIN_RST)
        self._port.write(bytes([data & 0xFF]))

    def _data_buf(self, buf: bytes) -> None:
        self._write_gpio(PIN_DC | PIN_RST)
        # Chunk to avoid huge USB transfers
        chunk = 2048
        for i in range(0, len(buf), chunk):
            self._port.write(buf[i : i + chunk])

    def read_busy(self) -> bool:
        """Return True if panel reports busy (pin high per Waveshare wait loop)."""
        level = self._gpio.read()
        return bool(level & PIN_BUSY)

    def wait_ready(self, timeout_s: float = 30.0) -> None:
        """
        Waveshare V2 code waits while busy_pin == 1.
        Timeout so a wiring mistake cannot hang forever.
        """
        t0 = time.monotonic()
        # brief settle
        time.sleep(0.01)
        while self.read_busy():
            if time.monotonic() - t0 > timeout_s:
                raise TimeoutError(
                    f"e-Paper still BUSY after {timeout_s}s "
                    f"(gpio={self._gpio.read():#04x}). Check wiring."
                )
            time.sleep(0.02)
        logger.debug("busy cleared in %.2fs", time.monotonic() - t0)

    def turn_on_display(self) -> None:
        self._cmd(0x22)
        self._data(0xF7)
        self._cmd(0x20)
        self.wait_ready()

    def init(self) -> None:
        self.reset()
        self.wait_ready(timeout_s=5.0)
        self._cmd(0x12)  # SWRESET
        self.wait_ready()

        self._cmd(0x45)  # RAM Y start/end
        self._data(0x00)
        self._data(0x00)
        self._data(0x07)  # 263
        self._data(0x01)

        self._cmd(0x4F)
        self._data(0x00)
        self._data(0x00)

        self._cmd(0x11)  # data entry mode
        self._data(0x03)
        logger.info("Panel init OK")

    def clear(self) -> None:
        width_bytes = EPD_WIDTH // 8
        white = bytes([0xFF]) * (width_bytes * EPD_HEIGHT)
        self._cmd(0x24)
        self._data_buf(white)
        self.turn_on_display()

    def display_buffer(self, buf: bytes) -> None:
        expected = (EPD_WIDTH // 8) * EPD_HEIGHT
        if len(buf) != expected:
            raise ValueError(f"buffer size {len(buf)} != {expected}")
        self._cmd(0x24)
        self._data_buf(buf)
        self.turn_on_display()

    def sleep(self) -> None:
        self._cmd(0x10)
        self._data(0x01)
        time.sleep(0.1)

    @staticmethod
    def image_to_buffer(image) -> bytes:
        """Convert PIL image to Waveshare 1-bit buffer (portrait 176×264 native)."""
        from PIL import Image

        if image.size != (EPD_WIDTH, EPD_HEIGHT):
            # Accept landscape 264×176 UI frames and rotate into panel native.
            if image.size == (EPD_HEIGHT, EPD_WIDTH):
                image = image.transpose(Image.Transpose.ROTATE_90)
            else:
                image = image.convert("1").resize((EPD_WIDTH, EPD_HEIGHT))
        mono = image.convert("1")
        pixels = mono.load()
        buf = bytearray([0xFF] * ((EPD_WIDTH // 8) * EPD_HEIGHT))
        for y in range(EPD_HEIGHT):
            for x in range(EPD_WIDTH):
                if pixels[x, y] == 0:  # black
                    buf[(x + y * EPD_WIDTH) // 8] &= ~(0x80 >> (x % 8))
        return bytes(buf)


def _make_demo_image():
    from PIL import Image, ImageDraw, ImageFont

    # Landscape UI size then driver rotates
    img = Image.new("1", (264, 176), 1)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 263, 16), fill=0)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 14)
        font_sm = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 11)
    except OSError:
        font = ImageFont.load_default()
        font_sm = font
    d.text((6, 2), "WROLPi e-Paper", font=font_sm, fill=1)
    d.text((10, 40), "FlipTDI SPI OK", font=font, fill=0)
    d.text((10, 70), "2.7 inch test", font=font, fill=0)
    d.rectangle((10, 100, 120, 150), outline=0, width=2)
    d.text((18, 115), "Hello!", font=font, fill=0)
    return img


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Waveshare 2.7\" via Flipper FlipTDI")
    p.add_argument("action", choices=("probe", "clear", "demo", "image"))
    p.add_argument("path", nargs="?", help="PNG path for 'image'")
    p.add_argument("--url", default=None, help="pyftdi URL override")
    p.add_argument("--hz", type=float, default=2e6, help="SPI clock Hz")
    args = p.parse_args(argv)

    epd = FlipTdiEpd27(url=args.url, spi_hz=args.hz)
    try:
        if args.action == "probe":
            print(f"url={epd.url}")
            print(f"BUSY={epd.read_busy()} gpio={epd._gpio.read():#04x}")
            epd.reset()
            print(f"after reset BUSY={epd.read_busy()} gpio={epd._gpio.read():#04x}")
            return 0

        print("Init…")
        epd.init()
        if args.action == "clear":
            print("Clear (full refresh, ~few seconds)…")
            epd.clear()
        elif args.action == "demo":
            print("Demo image…")
            img = _make_demo_image()
            epd.display_buffer(epd.image_to_buffer(img))
        elif args.action == "image":
            from PIL import Image

            if not args.path:
                print("image requires path", file=sys.stderr)
                return 2
            img = Image.open(args.path)
            print(f"Display {args.path} size={img.size}…")
            epd.display_buffer(epd.image_to_buffer(img))
        print("Sleep panel…")
        epd.sleep()
        print("Done.")
        return 0
    except Exception as e:
        logger.exception("Failed: %s", e)
        return 1
    finally:
        epd.close()


if __name__ == "__main__":
    raise SystemExit(main())
