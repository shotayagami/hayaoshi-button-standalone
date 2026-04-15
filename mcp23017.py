from machine import I2C

# MCP23017 registers
_IODIRA = 0x00   # Direction register A
_IODIRB = 0x01   # Direction register B
_GPPUA = 0x0C    # Pull-up register A
_GPPUB = 0x0D    # Pull-up register B
_GPIOA = 0x12    # Port A read
_GPIOB = 0x13    # Port B read
_OLATB = 0x15    # Port B output latch


class MCP23017:
    """MCP23017 I2C GPIO expander driver."""

    def __init__(self, i2c, address=0x20):
        self.i2c = i2c
        self.address = address
        self._buf1 = bytearray(1)

    def init(self):
        """Configure GPA as inputs with pull-ups (host buttons)."""
        self.i2c.writeto_mem(self.address, _IODIRA, bytes([0xFF]))
        self.i2c.writeto_mem(self.address, _IODIRB, bytes([0xFF]))
        self.i2c.writeto_mem(self.address, _GPPUA, bytes([0x7F]))
        print("MCP23017: initialized at 0x{:02X}".format(self.address))

    def init_port_b(self, iodir, pullup=0x00, initial=0x00):
        """Configure GPB direction, pull-ups, and initial output.
        iodir: bit=1 input, bit=0 output.
        """
        self.i2c.writeto_mem(self.address, _IODIRB, bytes([iodir]))
        self.i2c.writeto_mem(self.address, _GPPUB, bytes([pullup]))
        self.i2c.writeto_mem(self.address, _OLATB, bytes([initial]))

    def read_port_a(self):
        """Read GPIOA (8 bits). 1=released, 0=pressed."""
        data = self.i2c.readfrom_mem(self.address, _GPIOA, 1)
        return data[0]

    def read_port_b(self):
        """Read GPIOB (8 bits)."""
        data = self.i2c.readfrom_mem(self.address, _GPIOB, 1)
        return data[0]

    def write_port_b(self, val):
        """Write OLATB (8 bits). Only affects pins configured as output."""
        self._buf1[0] = val
        self.i2c.writeto_mem(self.address, _OLATB, self._buf1)

    @staticmethod
    def scan(i2c):
        """Scan I2C bus for MCP23017 (address range 0x20-0x27)."""
        devices = i2c.scan()
        for addr in devices:
            if 0x20 <= addr <= 0x27:
                return addr
        return None
