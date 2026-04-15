from machine import I2C

# MCP23017 registers
_IODIRA = 0x00   # Direction register A
_IODIRB = 0x01   # Direction register B
_GPPUA = 0x0C    # Pull-up register A
_GPIOA = 0x12    # Port A read


class MCP23017:
    """MCP23017 I2C GPIO expander driver for host buttons."""

    def __init__(self, i2c, address=0x20):
        self.i2c = i2c
        self.address = address

    def init(self):
        """Configure GPA0-GPA6 as inputs with pull-ups."""
        # GPA all inputs (0xFF)
        self.i2c.writeto_mem(self.address, _IODIRA, bytes([0xFF]))
        # GPB all inputs (0xFF)
        self.i2c.writeto_mem(self.address, _IODIRB, bytes([0xFF]))
        # Enable pull-ups on GPA0-GPA6
        self.i2c.writeto_mem(self.address, _GPPUA, bytes([0x7F]))
        print("MCP23017: initialized at 0x{:02X}".format(self.address))

    def read_port_a(self):
        """Read all 8 bits of GPIOA. Returns byte value.
        Each bit: 1=released, 0=pressed (active-low).
        """
        data = self.i2c.readfrom_mem(self.address, _GPIOA, 1)
        return data[0]

    @staticmethod
    def scan(i2c):
        """Scan I2C bus for MCP23017 (address range 0x20-0x27)."""
        devices = i2c.scan()
        for addr in devices:
            if 0x20 <= addr <= 0x27:
                return addr
        return None
