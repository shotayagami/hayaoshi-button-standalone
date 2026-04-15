# ILI9341 TFT Display Driver for MicroPython (Pure Python, SPI)
# 2.8" 240x320 RGB565, with touch (XPT2046 on separate SPI).

from machine import Pin, SPI
import time
import struct


class ILI9341:
    """ILI9341 240x320 TFT driver. Colors are RGB565 big-endian."""

    def __init__(self, spi, cs, dc, rst=None, width=240, height=320, rotation=0):
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.rst = rst
        self._width = width
        self._height = height
        self.rotation = rotation
        if rotation in (1, 3):
            self.width = height
            self.height = width
        else:
            self.width = width
            self.height = height
        self._buf1 = bytearray(1)
        self.cs.value(1)

    def init(self):
        """Initialize display. Call once after power-up."""
        # Hardware reset
        if self.rst:
            self.rst.value(1)
            time.sleep_ms(50)
            self.rst.value(0)
            time.sleep_ms(50)
            self.rst.value(1)
            time.sleep_ms(150)

        self._cmd(0x01)  # Software reset
        time.sleep_ms(150)

        # Power control
        self._cmd(0xCB, b'\x39\x2C\x00\x34\x02')  # Power control A
        self._cmd(0xCF, b'\x00\xC1\x30')            # Power control B
        self._cmd(0xE8, b'\x85\x00\x78')             # Driver timing control A
        self._cmd(0xEA, b'\x00\x00')                  # Driver timing control B
        self._cmd(0xED, b'\x64\x03\x12\x81')         # Power on sequence control
        self._cmd(0xF7, b'\x20')                      # Pump ratio control
        self._cmd(0xC0, b'\x23')                      # Power control 1 (VRH=4.60V)
        self._cmd(0xC1, b'\x10')                      # Power control 2
        self._cmd(0xC5, b'\x3E\x28')                  # VCOM control 1
        self._cmd(0xC7, b'\x86')                      # VCOM control 2

        # Display settings
        self._cmd(0x36, bytes([self._madctl()]))      # MADCTL: rotation + BGR
        self._cmd(0x3A, b'\x55')                      # COLMOD: 16-bit RGB565
        self._cmd(0xB1, b'\x00\x18')                  # Frame rate: 79Hz
        self._cmd(0xB6, b'\x08\x82\x27')             # Display function control

        # Gamma
        self._cmd(0x26, b'\x01')                      # Gamma set: curve 1
        self._cmd(0xE0, b'\x0F\x31\x2B\x0C\x0E\x08'  # Positive gamma
                        b'\x4E\xF1\x37\x07\x10\x03'
                        b'\x0E\x09\x00')
        self._cmd(0xE1, b'\x00\x0E\x14\x03\x11\x07'  # Negative gamma
                        b'\x31\xC1\x48\x08\x0F\x0C'
                        b'\x31\x36\x0F')

        self._cmd(0x11)  # Sleep out
        time.sleep_ms(120)
        self._cmd(0x29)  # Display on
        time.sleep_ms(50)

    def _madctl(self):
        """MADCTL register value for rotation (BGR subpixel order)."""
        # MY=bit7, MX=bit6, MV=bit5, BGR=bit3
        return (0x48, 0x28, 0x88, 0xE8)[self.rotation % 4]

    def _cmd(self, cmd, data=None):
        """Write command (and optional data) to display."""
        self.cs.value(0)
        self.dc.value(0)
        self._buf1[0] = cmd
        self.spi.write(self._buf1)
        if data:
            self.dc.value(1)
            self.spi.write(data)
        self.cs.value(1)

    def _set_window(self, x0, y0, x1, y1):
        """Set draw window (CASET + RASET + RAMWR)."""
        self._cmd(0x2A, struct.pack('>HH', x0, x1))
        self._cmd(0x2B, struct.pack('>HH', y0, y1))
        self._cmd(0x2C)

    def fill_rect(self, x, y, w, h, color):
        """Fill rectangle with solid RGB565 color."""
        if w <= 0 or h <= 0:
            return
        self._set_window(x, y, x + w - 1, y + h - 1)
        hi = (color >> 8) & 0xFF
        lo = color & 0xFF
        chunk_px = min(w * h, w * 4)
        chunk = bytearray(chunk_px * 2)
        for i in range(0, len(chunk), 2):
            chunk[i] = hi
            chunk[i + 1] = lo
        self.cs.value(0)
        self.dc.value(1)
        total = w * h
        while total > 0:
            n = min(total, chunk_px)
            if n == chunk_px:
                self.spi.write(chunk)
            else:
                self.spi.write(memoryview(chunk)[:n * 2])
            total -= n
        self.cs.value(1)

    def fill(self, color):
        """Fill entire screen with solid color."""
        self.fill_rect(0, 0, self.width, self.height, color)

    def blit_buffer(self, buf, x, y, w, h):
        """Write raw RGB565 pixel buffer to display region."""
        self._set_window(x, y, x + w - 1, y + h - 1)
        self.cs.value(0)
        self.dc.value(1)
        self.spi.write(buf)
        self.cs.value(1)

    @staticmethod
    def color565(r, g, b):
        """Convert RGB888 to RGB565."""
        return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
