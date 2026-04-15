# XPT2046 Touch Controller Driver
# Bit-banged SPI via MCP23017 GPB port.
#
# GPB pin mapping:
#   GPB0 = CS   (output, active LOW)
#   GPB1 = CLK  (output)
#   GPB2 = DIN  (MOSI, output)
#   GPB3 = DOUT (MISO, input)
#   GPB4 = IRQ  (input, active LOW = touched)

_CS  = 0x01  # GPB0
_CLK = 0x02  # GPB1
_DIN = 0x04  # GPB2
_DOUT = 0x08  # GPB3
_IRQ = 0x10  # GPB4

# XPT2046 control byte commands (12-bit, differential, power-down between)
_CMD_X = 0xD0  # Read X position
_CMD_Y = 0x90  # Read Y position
_CMD_Z1 = 0xB0  # Read Z1 (pressure)

# GPB direction: GPB0-2 output, GPB3-7 input
IODIR_B = 0xF8
# Pull-ups on input pins (DOUT, IRQ, spare)
PULLUP_B = 0xF8
# Initial state: CS=HIGH, CLK=LOW, DIN=LOW
INITIAL_B = _CS


class XPT2046:
    """XPT2046 resistive touch controller via MCP23017 GPB bit-bang SPI."""

    def __init__(self, mcp, width=240, height=320):
        self.mcp = mcp
        self.width = width
        self.height = height
        self._out = INITIAL_B  # current GPB output state
        # Calibration: raw ADC range -> pixel range
        # Defaults for typical 2.4" 240x320 module (adjust after testing)
        self.cal_x_min = 200
        self.cal_x_max = 3900
        self.cal_y_min = 200
        self.cal_y_max = 3900
        self._ready = False

    def init(self):
        """Configure MCP23017 GPB for touch SPI."""
        self.mcp.init_port_b(IODIR_B, PULLUP_B, INITIAL_B)
        self._out = INITIAL_B
        self._ready = True
        print("XPT2046: initialized via MCP23017 GPB")

    def is_ready(self):
        return self._ready

    def _set_out(self, val):
        """Write GPB output bits."""
        self._out = val
        self.mcp.write_port_b(val)

    def _read_in(self):
        """Read GPB input bits."""
        return self.mcp.read_port_b()

    def _spi_transfer_byte(self, byte_out):
        """Bit-bang one byte out (MSB first), return byte read in."""
        byte_in = 0
        for i in range(8):
            # Set MOSI bit
            bit = (byte_out >> (7 - i)) & 1
            out = self._out & ~(_CLK | _DIN)
            if bit:
                out |= _DIN
            self._set_out(out)
            # Clock high -> sample MISO
            self._set_out(out | _CLK)
            inp = self._read_in()
            if inp & _DOUT:
                byte_in |= (1 << (7 - i))
            # Clock low
            self._set_out(out)
        return byte_in

    def _read_channel(self, cmd):
        """Send command and read 12-bit ADC result."""
        # CS low
        self._set_out(self._out & ~_CS)
        # Send command byte
        self._spi_transfer_byte(cmd)
        # Read 2 bytes (12-bit result in bits [14:3])
        hi = self._spi_transfer_byte(0x00)
        lo = self._spi_transfer_byte(0x00)
        # CS high
        self._set_out(self._out | _CS)
        return ((hi << 8) | lo) >> 3

    def is_touched(self):
        """Check IRQ pin (active LOW = touched)."""
        if not self._ready:
            return False
        inp = self._read_in()
        return (inp & _IRQ) == 0

    def read_raw(self):
        """Read raw X, Y ADC values. Returns (x, y) or None if not touched."""
        if not self._ready:
            return None
        x = self._read_channel(_CMD_X)
        y = self._read_channel(_CMD_Y)
        if x < 100 and y < 100:
            return None  # no touch
        return (x, y)

    def read_pos(self):
        """Read calibrated screen position. Returns (px, py) or None."""
        raw = self.read_raw()
        if raw is None:
            return None
        rx, ry = raw
        # Clamp and map to screen coordinates
        px = (rx - self.cal_x_min) * self.width // (self.cal_x_max - self.cal_x_min)
        py = (ry - self.cal_y_min) * self.height // (self.cal_y_max - self.cal_y_min)
        px = max(0, min(self.width - 1, px))
        py = max(0, min(self.height - 1, py))
        return (px, py)

    def set_calibration(self, x_min, x_max, y_min, y_max):
        """Set raw ADC -> pixel calibration values."""
        self.cal_x_min = x_min
        self.cal_x_max = x_max
        self.cal_y_min = y_min
        self.cal_y_max = y_max
