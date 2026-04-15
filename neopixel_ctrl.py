import neopixel
from machine import Pin
import asyncio
import protocol


class NeoPixelController:
    """WS2812B NeoPixel LED strip controller for player colors."""

    BRIGHTNESS_FULL = 1.0
    BRIGHTNESS_DIM = 0.1
    BRIGHTNESS_OFF = 0.0

    def __init__(self, pin_num=28, num_leds=8):
        self.np = neopixel.NeoPixel(Pin(pin_num), num_leds)
        self.num_leds = num_leds
        self._colors = [(0, 0, 0)] * num_leds  # Base RGB colors
        self.clear()
        print(f"NeoPixel: {num_leds} LEDs on GP{pin_num}")

    @staticmethod
    def hex_to_rgb(hex_color):
        """Convert '#RRGGBB' to (R, G, B) tuple."""
        h = hex_color.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    def _scale(self, rgb, brightness):
        """Scale RGB tuple by brightness (0.0-1.0)."""
        return (
            int(rgb[0] * brightness),
            int(rgb[1] * brightness),
            int(rgb[2] * brightness),
        )

    def set_color(self, led_id, r, g, b, brightness=1.0):
        """Set LED color with brightness."""
        if 0 <= led_id < self.num_leds:
            self._colors[led_id] = (r, g, b)
            self.np[led_id] = self._scale((r, g, b), brightness)

    def set_color_hex(self, led_id, hex_color, brightness=1.0):
        """Set LED from hex color string."""
        rgb = self.hex_to_rgb(hex_color)
        self.set_color(led_id, rgb[0], rgb[1], rgb[2], brightness)

    def clear(self):
        """Turn off all LEDs."""
        for i in range(self.num_leds):
            self.np[i] = (0, 0, 0)
            self._colors[i] = (0, 0, 0)
        self.np.write()

    def show(self):
        """Write buffered colors to the strip."""
        self.np.write()

    def update_from_game(self, state, colors, press_order,
                         answerer_id, num_players, answerer_idx):
        """Update all LEDs based on current game state."""
        if state == protocol.STATE_IDLE:
            # All off
            for i in range(self.num_leds):
                self.np[i] = (0, 0, 0)

        elif state == protocol.STATE_ARMED:
            # All players show their color at dim
            for i in range(num_players):
                if i < len(colors):
                    rgb = self.hex_to_rgb(colors[i])
                    self.np[i] = self._scale(rgb, self.BRIGHTNESS_DIM)
                else:
                    self.np[i] = (0, 0, 0)
            for i in range(num_players, self.num_leds):
                self.np[i] = (0, 0, 0)

        elif state in (protocol.STATE_JUDGING, protocol.STATE_SHOWING_RESULT):
            pressed_ids = {pid for pid, _ in press_order}
            for i in range(num_players):
                if i < len(colors):
                    rgb = self.hex_to_rgb(colors[i])
                else:
                    rgb = (128, 128, 128)

                if i == answerer_id:
                    # Current answerer: full brightness
                    self.np[i] = self._scale(rgb, self.BRIGHTNESS_FULL)
                elif i in pressed_ids:
                    # Find position in press_order
                    pos = next(
                        (idx for idx, (pid, _) in enumerate(press_order) if pid == i),
                        -1,
                    )
                    if pos >= 0 and pos > answerer_idx:
                        # Waiting: dim
                        self.np[i] = self._scale(rgb, self.BRIGHTNESS_DIM)
                    else:
                        # Already answered: off
                        self.np[i] = (0, 0, 0)
                else:
                    # Not pressed: off
                    self.np[i] = (0, 0, 0)

            for i in range(num_players, self.num_leds):
                self.np[i] = (0, 0, 0)

        self.np.write()

    async def flash_led(self, led_id, hex_color, times=20, interval_ms=75):
        """Flash animation for correct answer."""
        rgb = self.hex_to_rgb(hex_color)
        for _ in range(times):
            self.np[led_id] = rgb
            self.np.write()
            await asyncio.sleep(0.001 * interval_ms)
            self.np[led_id] = (0, 0, 0)
            self.np.write()
            await asyncio.sleep(0.001 * interval_ms)
