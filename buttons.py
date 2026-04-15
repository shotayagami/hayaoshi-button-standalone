from machine import Pin, PWM
import time
import asyncio


class ButtonManager:
    DEBOUNCE_US = 20_000  # 20ms
    PWM_FREQ = 1000
    BRIGHTNESS_FULL = 65535
    BRIGHTNESS_DIM = 6500
    BRIGHTNESS_OFF = 0

    # Host button name -> MCP23017 GPA bit mapping
    HOST_BUTTON_BITS = {
        "correct": 0,
        "incorrect": 1,
        "reset": 2,
        "arm": 3,
        "stop": 4,
        "jingle": 5,
        "countdown": 6,
    }

    def __init__(self, num_players=8, mcp=None):
        self.num_players = num_players
        self._mcp = mcp

        # Player buttons (active LOW with pull-up)
        # GP0-GP3, GP26, GP27, GP6, GP7 (GP4/GP5 reserved for UART1/DFPlayer)
        PLAYER_GPIOS = [0, 1, 2, 3, 26, 27, 6, 7]
        self.player_pins = [
            Pin(PLAYER_GPIOS[i], Pin.IN, Pin.PULL_UP) for i in range(num_players)
        ]

        # Player lamps: GP8-GP15 (PWM output)
        self.lamp_pwms = []
        for i in range(num_players):
            pwm = PWM(Pin(i + 8))
            pwm.freq(self.PWM_FREQ)
            pwm.duty_u16(0)
            self.lamp_pwms.append(pwm)

        # Host buttons: MCP23017 or direct GPIO
        if mcp:
            self.host_pins = None
            print("ButtonManager: host buttons via MCP23017")
        else:
            self.host_pins = {
                "correct": Pin(16, Pin.IN, Pin.PULL_UP),
                "incorrect": Pin(17, Pin.IN, Pin.PULL_UP),
                "reset": Pin(18, Pin.IN, Pin.PULL_UP),
                "arm": Pin(19, Pin.IN, Pin.PULL_UP),
                "stop": Pin(20, Pin.IN, Pin.PULL_UP),
                "jingle": Pin(21, Pin.IN, Pin.PULL_UP),
                "countdown": Pin(22, Pin.IN, Pin.PULL_UP),
            }
            print("ButtonManager: host buttons via direct GPIO")

        # Debounce tracking
        self._player_last_us = [0] * num_players
        self._player_prev = [1] * num_players
        host_names = list(self.HOST_BUTTON_BITS.keys())
        self._host_last_us = {k: 0 for k in host_names}
        self._host_prev = {k: 1 for k in host_names}

        # Flash task tracking
        self._flash_task = None

        # Callbacks
        self._on_player_press = None
        self._on_host_press = None

    def set_player_callback(self, callback):
        """callback(player_id: int, timestamp_us: int)"""
        self._on_player_press = callback

    def set_host_callback(self, callback):
        """callback(button_name: str)"""
        self._on_host_press = callback

    # Lamp control
    def lamp_full(self, player_id):
        if 0 <= player_id < self.num_players:
            self.lamp_pwms[player_id].duty_u16(self.BRIGHTNESS_FULL)

    def lamp_dim(self, player_id):
        if 0 <= player_id < self.num_players:
            self.lamp_pwms[player_id].duty_u16(self.BRIGHTNESS_DIM)

    def lamp_off(self, player_id):
        if 0 <= player_id < self.num_players:
            self.lamp_pwms[player_id].duty_u16(self.BRIGHTNESS_OFF)

    def all_lamps_off(self):
        for pwm in self.lamp_pwms:
            pwm.duty_u16(self.BRIGHTNESS_OFF)

    # Backward compatibility
    def lamp_on(self, player_id):
        self.lamp_full(player_id)

    def start_blink(self, player_id, interval_ms=300):
        self.lamp_full(player_id)

    def stop_blink(self):
        pass

    async def flash_lamp(self, player_id, times=3, interval_ms=200):
        for _ in range(times):
            self.lamp_full(player_id)
            await asyncio.sleep(0.001 * interval_ms)
            self.lamp_off(player_id)
            await asyncio.sleep(0.001 * interval_ms)

    # Polling loop
    async def poll_loop(self):
        while True:
            now = time.ticks_us()

            # Poll player buttons (edge detection)
            for i in range(self.num_players):
                val = self.player_pins[i].value()
                prev = self._player_prev[i]
                self._player_prev[i] = val
                if val == 0 and prev == 1:  # falling edge
                    if time.ticks_diff(now, self._player_last_us[i]) > self.DEBOUNCE_US:
                        self._player_last_us[i] = now
                        if self._on_player_press:
                            await self._on_player_press(i, now)

            # Poll host buttons
            if self._mcp:
                # MCP23017: read all bits at once
                port_val = self._mcp.read_port_a()
                for name, bit in self.HOST_BUTTON_BITS.items():
                    val = (port_val >> bit) & 1
                    prev = self._host_prev[name]
                    self._host_prev[name] = val
                    if val == 0 and prev == 1:
                        if time.ticks_diff(now, self._host_last_us[name]) > self.DEBOUNCE_US:
                            self._host_last_us[name] = now
                            if self._on_host_press:
                                await self._on_host_press(name)
            else:
                # Direct GPIO
                for name, pin in self.host_pins.items():
                    val = pin.value()
                    prev = self._host_prev[name]
                    self._host_prev[name] = val
                    if val == 0 and prev == 1:
                        if time.ticks_diff(now, self._host_last_us[name]) > self.DEBOUNCE_US:
                            self._host_last_us[name] = now
                            if self._on_host_press:
                                await self._on_host_press(name)

            await asyncio.sleep(0.001)
