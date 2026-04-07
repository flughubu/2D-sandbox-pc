"""
HUD: hotbar, mining progress bar, block tooltip, day/night clock, coordinates.
"""
from __future__ import annotations

import os
import math
from typing import TYPE_CHECKING

import pygame

from tiles import HOTBAR_DEFAULTS, BLOCK_NAMES, AIR

if TYPE_CHECKING:
    from renderer import Renderer
    from player import Player

ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "apk_extracted", "assets", "GameResources",
)

# ── Colours ───────────────────────────────────────────────────────────────────
COL_SLOT_BG     = (30,  30,  30,  180)
COL_SLOT_BORDER = (80,  80,  80,  220)
COL_SLOT_SEL    = (255, 200,  50,  230)
COL_MINE_BG     = (20,  20,  20,  180)
COL_MINE_BAR    = (255, 160,  20,  220)
COL_TEXT        = (255, 255, 255)
COL_TEXT_SHADOW = (0,   0,   0)
COL_TOOLTIP_BG  = (20,  20,  20,  200)


class HUD:
    """Draws the game HUD on top of the world."""

    SLOT_SIZE   = 52    # pixels per hotbar slot
    SLOT_PAD    =  4
    SLOTS       =  9

    def __init__(self, screen: pygame.Surface, renderer: "Renderer"):
        self.screen   = screen
        self.renderer = renderer
        self.sw, self.sh = screen.get_size()

        # Hotbar
        self.hotbar:    list[int] = list(HOTBAR_DEFAULTS)
        self.sel_slot:  int       = 0

        # Font
        font_path = os.path.join(ASSETS_DIR, "Fonts", "BlockheadsFont-Regular.otf")
        if os.path.exists(font_path):
            self.font_sm = pygame.font.Font(font_path, 14)
            self.font_md = pygame.font.Font(font_path, 18)
        else:
            self.font_sm = pygame.font.SysFont("monospace", 13)
            self.font_md = pygame.font.SysFont("monospace", 16)

        # Pre-render slot background surfaces
        self._slot_bg     = self._make_slot_surf(False)
        self._slot_sel_bg = self._make_slot_surf(True)

        # Tooltip state
        self._tooltip_block: int | None = None
        self._tooltip_timer: int        = 0   # frames to show

    # ── Main draw ─────────────────────────────────────────────────────────────

    def draw(self, player: "Player", time_of_day: float,
             hovered_block: int | None = None) -> None:
        self.sw, self.sh = self.screen.get_size()

        self._draw_hotbar()
        self._draw_mining_bar(player)
        self._draw_clock(time_of_day)
        self._draw_coords(player)

        if hovered_block and hovered_block != AIR:
            self._draw_tooltip(hovered_block)

        # Keybind hints at the very bottom
        self._draw_hints()

    # ── Hotbar ────────────────────────────────────────────────────────────────

    def _draw_hotbar(self) -> None:
        SS   = self.SLOT_SIZE
        PAD  = self.SLOT_PAD
        n    = self.SLOTS
        total_w = n * (SS + PAD) - PAD
        ox = (self.sw - total_w) // 2
        oy = self.sh - SS - 12

        for i, block in enumerate(self.hotbar):
            sx = ox + i * (SS + PAD)
            bg = self._slot_sel_bg if i == self.sel_slot else self._slot_bg
            self.screen.blit(bg, (sx, oy))

            if block != AIR:
                icon_rect = pygame.Rect(sx + 6, oy + 6, SS - 12, SS - 12)
                self.renderer.draw_block_icon(block, icon_rect)

            # Slot number
            num = self._render_text(str(i + 1), self.font_sm, COL_TEXT,
                                    shadow=True)
            self.screen.blit(num, (sx + 4, oy + 4))

    def _make_slot_surf(self, selected: bool) -> pygame.Surface:
        SS = self.SLOT_SIZE
        s  = pygame.Surface((SS, SS), pygame.SRCALPHA)
        s.fill(COL_SLOT_BG)
        border_col = COL_SLOT_SEL if selected else COL_SLOT_BORDER
        pygame.draw.rect(s, border_col, s.get_rect(), 3)
        if selected:
            glow = pygame.Surface((SS, SS), pygame.SRCALPHA)
            glow.fill((255, 200, 50, 25))
            s.blit(glow, (0, 0))
        return s

    # ── Mining progress bar ───────────────────────────────────────────────────

    def _draw_mining_bar(self, player: "Player") -> None:
        if player.mining_target is None or player.mining_progress <= 0:
            return

        bar_w, bar_h = 160, 14
        ox = (self.sw - bar_w) // 2
        oy = self.sh - self.SLOT_SIZE - 12 - bar_h - 8

        # Background
        bg = pygame.Surface((bar_w + 4, bar_h + 4), pygame.SRCALPHA)
        bg.fill(COL_MINE_BG)
        self.screen.blit(bg, (ox - 2, oy - 2))

        # Fill
        fill_w = int(bar_w * player.mining_progress)
        if fill_w > 0:
            pygame.draw.rect(self.screen, COL_MINE_BAR,
                             (ox, oy, fill_w, bar_h))

        # Border
        pygame.draw.rect(self.screen, (180, 180, 180),
                         (ox, oy, bar_w, bar_h), 1)

    # ── Clock / day indicator ─────────────────────────────────────────────────

    def _draw_clock(self, time_of_day: float) -> None:
        cx, cy = self.sw - 40, 40
        r = 24

        # Clock face
        pygame.draw.circle(self.screen, (30, 30, 30, 180), (cx, cy), r)
        pygame.draw.circle(self.screen, (120, 120, 120), (cx, cy), r, 2)

        # Sun or moon
        angle = (time_of_day - 0.5) * math.tau   # noon = top
        hand_x = cx + int(r * 0.65 * math.sin(angle))
        hand_y = cy - int(r * 0.65 * math.cos(angle))

        is_day = 0.2 <= time_of_day <= 0.8
        orb_col = (255, 220, 50) if is_day else (200, 200, 230)
        orb_r   = 8 if is_day else 6
        pygame.draw.circle(self.screen, orb_col, (hand_x, hand_y), orb_r)

    # ── Coordinate display ────────────────────────────────────────────────────

    def _draw_coords(self, player: "Player") -> None:
        bx = int(player.x)
        by = int(player.y)
        txt = self._render_text(f"X:{bx}  Y:{by}", self.font_sm,
                                COL_TEXT, shadow=True)
        self.screen.blit(txt, (8, 8))

    # ── Block tooltip ─────────────────────────────────────────────────────────

    def _draw_tooltip(self, block: int) -> None:
        name = BLOCK_NAMES.get(block, "Unknown")
        txt  = self._render_text(name, self.font_md, COL_TEXT)
        pad  = 8
        w, h = txt.get_width() + pad * 2, txt.get_height() + pad * 2
        ox   = (self.sw - w) // 2
        oy   = self.sh - self.SLOT_SIZE - 12 - 36 - h - 4

        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        bg.fill(COL_TOOLTIP_BG)
        self.screen.blit(bg, (ox, oy))
        self.screen.blit(txt, (ox + pad, oy + pad))

    # ── Key-hint strip ────────────────────────────────────────────────────────

    def _draw_hints(self) -> None:
        hints = (
            "LClick:mine   RClick:place   1-9:hotbar   "
            "Scroll:cycle   WASD/Arrows:move   Space:jump"
        )
        surf = self._render_text(hints, self.font_sm, (200, 200, 200),
                                 shadow=True)
        self.screen.blit(surf, (self.sw // 2 - surf.get_width() // 2,
                                self.sh - self.SLOT_SIZE - 12 - 20))

    # ── Inventory overlay (full-screen, toggled with E) ───────────────────────

    def draw_inventory(self, inventory: list[int]) -> None:
        """Simple full-screen creative inventory overlay."""
        overlay = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        SS   = 48
        PAD  =  8
        COLS = 9
        rows = (len(inventory) + COLS - 1) // COLS
        total_w = COLS * (SS + PAD) - PAD
        total_h = rows * (SS + PAD) - PAD
        ox = (self.sw - total_w) // 2
        oy = (self.sh - total_h) // 2

        title = self._render_text("Inventory  [E to close]",
                                  self.font_md, COL_TEXT)
        self.screen.blit(title, (self.sw // 2 - title.get_width() // 2,
                                 oy - 32))

        for i, block in enumerate(inventory):
            r = i // COLS
            c = i  % COLS
            sx = ox + c * (SS + PAD)
            sy = oy + r * (SS + PAD)

            bg = pygame.Surface((SS, SS), pygame.SRCALPHA)
            bg.fill(COL_SLOT_BG)
            pygame.draw.rect(bg, COL_SLOT_BORDER, bg.get_rect(), 2)
            self.screen.blit(bg, (sx, sy))

            icon_rect = pygame.Rect(sx + 4, sy + 4, SS - 8, SS - 8)
            self.renderer.draw_block_icon(block, icon_rect)

        # Instructions
        note = self._render_text(
            "Click a block to add it to your hotbar",
            self.font_sm, (180, 180, 180))
        self.screen.blit(note, (self.sw // 2 - note.get_width() // 2,
                                oy + total_h + 12))

    def inventory_slot_at(self, mouse_pos: tuple[int, int],
                          inventory: list[int]) -> int | None:
        """Return inventory index under mouse, or None."""
        SS   = 48
        PAD  =  8
        COLS = 9
        rows = (len(inventory) + COLS - 1) // COLS
        total_w = COLS * (SS + PAD) - PAD
        total_h = rows * (SS + PAD) - PAD
        ox = (self.sw - total_w) // 2
        oy = (self.sh - total_h) // 2
        mx, my = mouse_pos
        for i in range(len(inventory)):
            r = i // COLS
            c = i  % COLS
            sx = ox + c * (SS + PAD)
            sy = oy + r * (SS + PAD)
            if sx <= mx < sx + SS and sy <= my < sy + SS:
                return i
        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _render_text(self, text: str, font: pygame.font.Font,
                     color: tuple, shadow: bool = False) -> pygame.Surface:
        if shadow:
            shadow_surf = font.render(text, True, COL_TEXT_SHADOW)
            main_surf   = font.render(text, True, color)
            w = main_surf.get_width() + 1
            h = main_surf.get_height() + 1
            out = pygame.Surface((w, h), pygame.SRCALPHA)
            out.blit(shadow_surf, (1, 1))
            out.blit(main_surf,   (0, 0))
            return out
        return font.render(text, True, color)

    # ── Hotbar selection ──────────────────────────────────────────────────────

    def scroll_slot(self, direction: int) -> None:
        self.sel_slot = (self.sel_slot + direction) % self.SLOTS

    def select_slot(self, index: int) -> None:
        if 0 <= index < self.SLOTS:
            self.sel_slot = index

    @property
    def selected_block(self) -> int:
        return self.hotbar[self.sel_slot]
