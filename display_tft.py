# TFT Display Controller for Hayaoshi Button System
# Renders game state on ST7789 240x320 TFT via SPI.
# Requires MCP23017 (host buttons on I2C frees GP18-22 for SPI).

import framebuf
import protocol


def _swap16(c):
    """Byte-swap RGB565 for framebuf (LE) <-> SPI (BE) compatibility."""
    return ((c >> 8) & 0xFF) | ((c & 0xFF) << 8)


def _hex565(h):
    """Convert '#RRGGBB' to RGB565."""
    if h[0] == '#':
        h = h[1:]
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


# Screen zones (y-start, height)
_SY, _SH = 0, 24       # Status bar
_MY, _MH = 24, 76      # Main display area
_OY, _OH = 100, 84     # Press order list
_CY, _CH = 184, 136    # Scoreboard

# Reset menu items: (label, action_name)
_MENU_ITEMS = [
    ("STOP (IDLE)", "reset"),
    ("Clear Penalty", "clear_penalty"),
    ("Reset Scores", "reset_scores"),
    ("Reset Round#", "reset_round"),
    ("FULL RESET", "reset_all"),
    ("Cancel", "cancel"),
]
_MENU_ITEM_H = 44       # Height per menu item
_MENU_Y0 = 36           # First item y-offset (after title)


class DisplayTFT:
    """Renders game state on a 240x320 ST7789 TFT display."""

    # Standard colors (RGB565)
    BLACK   = 0x0000
    WHITE   = 0xFFFF
    RED     = 0xF800
    GREEN   = 0x07E0
    BLUE    = 0x001F
    YELLOW  = 0xFFE0
    CYAN    = 0x07FF
    GRAY    = 0x8410
    DARK    = 0x2104

    def __init__(self, tft):
        self.tft = tft
        self.w = tft.width    # 240
        self.h = tft.height   # 320
        self.menu_active = False
        # Pre-allocated buffers for text rendering
        self._src = bytearray(240 * 8 * 2)       # 1x source (3840 B)
        self._row = bytearray(240 * 2)            # one scaled row (480 B)
        self._scl = bytearray(240 * 24 * 2)       # max scale-3 output (11520 B)

    # ── Text rendering ──────────────────────────────────────────

    def _text(self, s, x, y, fg, bg=0x0000, scale=1):
        """Draw text with integer scaling. Colors are normal RGB565."""
        if not s:
            return
        fb_fg = _swap16(fg)
        fb_bg = _swap16(bg)

        if scale == 1:
            n = min(len(s), (self.w - x) // 8)
            if n <= 0:
                return
            sw = n * 8
            fb = framebuf.FrameBuffer(self._src, sw, 8, framebuf.RGB565)
            fb.fill(fb_bg)
            fb.text(s[:n], 0, 0, fb_fg)
            self.tft.blit_buffer(memoryview(self._src)[:sw * 8 * 2], x, y, sw, 8)
            return

        n = min(len(s), (self.w - x) // (8 * scale))
        if n <= 0:
            return
        sw = n * 8       # source width in pixels
        dw = sw * scale   # dest width in pixels

        fb = framebuf.FrameBuffer(self._src, sw, 8, framebuf.RGB565)
        fb.fill(fb_bg)
        fb.text(s[:n], 0, 0, fb_fg)

        # Scale: duplicate each pixel horizontally and each row vertically
        for sr in range(8):
            so = sr * sw * 2
            do = 0
            for c in range(sw):
                b0 = self._src[so + c * 2]
                b1 = self._src[so + c * 2 + 1]
                for _ in range(scale):
                    self._row[do] = b0
                    self._row[do + 1] = b1
                    do += 2
            rb = dw * 2
            for sy in range(scale):
                oo = (sr * scale + sy) * rb
                self._scl[oo:oo + rb] = self._row[:rb]

        total = dw * 8 * scale * 2
        self.tft.blit_buffer(memoryview(self._scl)[:total], x, y, dw, 8 * scale)

    def _zone(self, y, h, color=0x0000):
        """Clear a screen zone with fill_rect."""
        self.tft.fill_rect(0, y, self.w, h, color)

    # ── Boot screen ─────────────────────────────────────────────

    def show_boot(self, ip, mode):
        """Show startup screen with IP address."""
        self.tft.fill(self.BLACK)
        self._text("Hayaoshi", 16, 40, self.WHITE, self.BLACK, 3)
        self._text("Button System", 12, 76, self.GRAY, self.BLACK, 2)
        self._text("IP: " + ip, 4, 140, self.GREEN, self.BLACK, 2)
        self._text("Mode: " + mode.upper(), 4, 164, self.CYAN, self.BLACK, 2)

    # ── Public API (called from game engine) ────────────────────

    def clear(self):
        self.tft.fill(self.BLACK)

    def refresh(self, game):
        """Full screen redraw from current game state."""
        self._draw_status(game.state, game.round)
        self._draw_main(game)
        self._draw_order(game)
        self._draw_scores(game)

    def on_arm(self, game):
        self._draw_status(game.state, game.round)
        self._draw_main(game)
        self._zone(_OY, _OH)
        self._draw_scores(game)

    def on_press(self, game):
        self._draw_status(game.state, game.round)
        self._draw_main(game)
        self._draw_order(game)

    def on_judge(self, result, player_id, delta, game):
        self._draw_status(game.state, game.round)
        self._draw_main_result(result, player_id, delta, game)
        self._draw_scores(game)

    def on_next_answerer(self, game):
        self._draw_main(game)
        self._draw_order(game)

    def on_idle(self, game):
        self._draw_status(game.state, game.round)
        self._draw_main(game)
        self._zone(_OY, _OH)

    def on_scores_update(self, game):
        self._draw_scores(game)

    # ── Zone renderers ──────────────────────────────────────────

    def _draw_status(self, state, round_num):
        """Status bar: state label + round number."""
        self._zone(_SY, _SH, self.DARK)
        labels = {
            protocol.STATE_IDLE: ("IDLE", self.GRAY),
            protocol.STATE_ARMED: ("ARMED", self.GREEN),
            protocol.STATE_JUDGING: ("JUDGING", self.YELLOW),
            protocol.STATE_SHOWING_RESULT: ("RESULT", self.CYAN),
        }
        label, color = labels.get(state, ("???", self.WHITE))
        self._text(label, 4, _SY + 4, color, self.DARK, 2)
        q = "Q.{:02d}".format(round_num)
        qw = len(q) * 16
        self._text(q, self.w - qw - 4, _SY + 4, self.WHITE, self.DARK, 2)

    def _draw_main(self, game):
        """Main area: depends on current state."""
        self._zone(_MY, _MH)
        if game.state == protocol.STATE_IDLE:
            self._text("Waiting...", 24, _MY + 26, self.GRAY, self.BLACK, 3)
        elif game.state == protocol.STATE_ARMED:
            self._text("READY!", 48, _MY + 26, self.GREEN, self.BLACK, 3)
        elif game.state == protocol.STATE_JUDGING:
            aid = game.get_current_answerer()
            if 0 <= aid < len(game.players):
                p = game.players[aid]
                c = _hex565(game.colors[aid]) if aid < len(game.colors) else self.WHITE
                self._text(p['name'][:10], 4, _MY + 10, c, self.BLACK, 3)
                self._text("Answering", 4, _MY + 46, self.GRAY, self.BLACK, 2)
        elif game.state == protocol.STATE_SHOWING_RESULT:
            self._text("Round Over", 20, _MY + 26, self.GRAY, self.BLACK, 3)

    def _draw_main_result(self, result, pid, delta, game):
        """Main area after judgment: show correct/incorrect."""
        self._zone(_MY, _MH)
        name = game.players[pid]['name'][:8] if pid < len(game.players) else "P{}".format(pid + 1)
        if result == protocol.RESULT_CORRECT:
            c = _hex565(game.colors[pid]) if pid < len(game.colors) else self.GREEN
            self._text("O " + name, 4, _MY + 6, c, self.BLACK, 3)
            self._text("+{}".format(delta), 4, _MY + 42, self.GREEN, self.BLACK, 3)
        else:
            self._text("X " + name, 4, _MY + 6, self.RED, self.BLACK, 3)
            self._text("{}".format(delta), 4, _MY + 42, self.RED, self.BLACK, 3)

    def _draw_order(self, game):
        """Press order list with time differences."""
        self._zone(_OY, _OH)
        if not game.press_order:
            return
        first_us = game._first_press_us
        for i, (pid, ts) in enumerate(game.press_order[:4]):
            name = game.players[pid]['name'][:7] if pid < len(game.players) else "P{}".format(pid + 1)
            if i == 0:
                line = "{}.{}".format(i + 1, name)
            else:
                diff = (ts - first_us) / 1_000_000
                line = "{}.{} +{:.3f}".format(i + 1, name, diff)
            c = _hex565(game.colors[pid]) if pid < len(game.colors) else self.WHITE
            self._text(line, 4, _OY + i * 20, c, self.BLACK, 2)

    def _draw_scores(self, game):
        """Scoreboard: two-column layout for up to 8 players."""
        self._zone(_CY, _CH)
        self.tft.fill_rect(0, _CY, self.w, 2, 0x4208)  # separator line
        half = (len(game.players) + 1) // 2
        for i, p in enumerate(game.players):
            col = 0 if i < half else 120
            row = i if i < half else i - half
            c = _hex565(game.colors[i]) if i < len(game.colors) else self.WHITE
            name = p['name'][:3]
            score = p['score']
            penalty = p.get('penalty', 0)
            if penalty > 0:
                c = self.GRAY
            line = "{:3s}{:4d}".format(name, score)
            self._text(line, col + 4, _CY + 8 + row * 20, c, self.BLACK, 2)

    # ── Touch reset menu ────────────────────────────────────────

    def show_reset_menu(self):
        """Draw full-screen reset menu. Sets menu_active flag."""
        self.tft.fill(self.BLACK)
        self._text("RESET MENU", 40, 6, self.WHITE, self.BLACK, 2)
        self.tft.fill_rect(0, 28, self.w, 2, self.GRAY)

        colors = [self.GRAY, 0xFD20, self.RED, self.BLUE, 0xC904, 0x4208]
        for i, (label, _) in enumerate(_MENU_ITEMS):
            y = _MENU_Y0 + i * _MENU_ITEM_H
            bg = colors[i] if i < len(colors) else self.DARK
            self.tft.fill_rect(4, y, self.w - 8, _MENU_ITEM_H - 4, bg)
            self._text(label, 12, y + 12, self.WHITE, bg, 2)

        self.menu_active = True

    def hide_reset_menu(self, game):
        """Close menu and restore normal display."""
        self.menu_active = False
        self.tft.fill(self.BLACK)
        self.refresh(game)

    def menu_hit_test(self, px, py):
        """Given touch pixel coords, return action name or None.
        Returns: 'reset', 'clear_penalty', 'reset_scores',
                 'reset_round', 'reset_all', or None (cancel/miss).
        """
        if not self.menu_active:
            return None
        for i, (_, action) in enumerate(_MENU_ITEMS):
            y = _MENU_Y0 + i * _MENU_ITEM_H
            if 4 <= px <= self.w - 4 and y <= py <= y + _MENU_ITEM_H - 4:
                return action
        return None
