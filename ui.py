"""
HUD: hotbar, full inventory, mining bar, tooltip, clock.
"""
from __future__ import annotations

import math
import os
from typing import TYPE_CHECKING

import pygame

from tiles import HOTBAR_DEFAULTS, BLOCK_NAMES, AIR, CREATIVE_PALETTE
from crafting import match_recipe, ITEM_NAMES

if TYPE_CHECKING:
    from renderer import Renderer
    from player   import Player

ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "apk_extracted", "assets", "GameResources",
)

# ── Colours ───────────────────────────────────────────────────────────────────
C_SLOT_BG    = (30,  30,  30,  180)
C_SLOT_BORD  = (80,  80,  80,  220)
C_SLOT_SEL   = (255, 200,  50,  230)
C_MINE_BAR   = (255, 160,  20,  220)
C_TEXT       = (255, 255, 255)
C_SHADOW     = (  0,   0,   0)
C_TOOLTIP_BG = ( 20,  20,  20,  200)
C_INV_BG     = ( 15,  20,  35,  230)
C_INV_HDR    = ( 40,  50,  80,  255)
C_DRAG_GHOST = (255, 255, 255,  120)


class HUD:
    SLOT_SIZE  = 52
    SLOT_PAD   =  4
    SLOTS      =  9

    def __init__(self, screen: pygame.Surface, renderer: "Renderer"):
        self.screen   = screen
        self.renderer = renderer
        self.sw, self.sh = screen.get_size()

        self.hotbar:   list[int] = list(HOTBAR_DEFAULTS)
        self.sel_slot: int       = 0

        # Player inventory (collected items)  slot → count
        self.inventory: list[int] = []    # ordered list of block types

        # Fonts
        fp = os.path.join(ASSETS_DIR, "Fonts", "BlockheadsFont-Regular.otf")
        if os.path.exists(fp):
            self.font_sm = pygame.font.Font(fp, 14)
            self.font_md = pygame.font.Font(fp, 18)
            self.font_lg = pygame.font.Font(fp, 24)
        else:
            self.font_sm = pygame.font.SysFont("monospace", 13)
            self.font_md = pygame.font.SysFont("monospace", 16)
            self.font_lg = pygame.font.SysFont("monospace", 20, bold=True)

        self._slot_bg  = self._make_slot(False)
        self._slot_sel = self._make_slot(True)

        # Inventory state
        self.show_inventory = False
        self._inv_tab       = 0    # 0=collected, 1=creative, 2=craft

        # Crafting grid (3×3, row-major, AIR=empty)
        self._craft_grid: list[int] = [AIR] * 9

        # Drag & drop
        self._drag_item:   int | None = None
        self._drag_origin: tuple[str, int] | None = None   # ("hotbar"|"inv", idx)
        self._drag_pos:    tuple[int, int] = (0, 0)

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
        self._draw_hints()

    def draw_inventory_overlay(self) -> None:
        """Full-screen inventory panel."""
        sw, sh = self.sw, self.sh

        # Semi-transparent backdrop
        bg = pygame.Surface((sw, sh), pygame.SRCALPHA)
        bg.fill(C_INV_BG)
        self.screen.blit(bg, (0, 0))

        panel_w, panel_h = min(700, sw - 40), min(540, sh - 40)
        px = (sw - panel_w) // 2
        py = (sh - panel_h) // 2

        # Panel background
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((20, 25, 45, 240))
        pygame.draw.rect(panel, (70, 80, 120), panel.get_rect(), 2)
        self.screen.blit(panel, (px, py))

        # Title bar
        hdr = pygame.Surface((panel_w, 36), pygame.SRCALPHA)
        hdr.fill(C_INV_HDR)
        self.screen.blit(hdr, (px, py))
        title = self._txt("Inventaire  [E pour fermer]", self.font_lg, C_TEXT)
        self.screen.blit(title, (px + 12, py + 6))

        # Tabs
        tab_labels = ["Collectés", "Créatif", "Artisanat"]
        tab_w = 100
        for i, lbl in enumerate(tab_labels):
            tx = px + panel_w - tab_w * (len(tab_labels) - i) - 8
            ty = py + 2
            col = (90, 110, 180) if i == self._inv_tab else (40, 50, 80)
            pygame.draw.rect(self.screen, col, (tx, ty, tab_w, 32))
            pygame.draw.rect(self.screen, (100, 120, 200), (tx, ty, tab_w, 32), 1)
            t = self._txt(lbl, self.font_sm, C_TEXT)
            self.screen.blit(t, (tx + tab_w // 2 - t.get_width() // 2, ty + 8))

        # Tab body
        if self._inv_tab == 2:
            self._draw_craft_tab(px, py, panel_w, panel_h)
        else:
            # Hotbar customization section
            self._draw_inv_hotbar_section(px, py, panel_w)
            # Item grid
            items = self.inventory if self._inv_tab == 0 else CREATIVE_PALETTE
            self._draw_inv_grid(items, px, py + 36 + 80, panel_w, panel_h - 36 - 80)

        # Drag ghost
        if self._drag_item is not None and self._drag_item != AIR:
            mx, my = self._drag_pos
            ghost = pygame.Surface((44, 44), pygame.SRCALPHA)
            self.renderer.draw_block_icon(self._drag_item,
                                          pygame.Rect(0, 0, 44, 44), ghost)
            ghost.set_alpha(160)
            self.screen.blit(ghost, (mx - 22, my - 22))

    def _draw_inv_hotbar_section(self, px: int, py: int, panel_w: int) -> None:
        """Draw the 9 hotbar slots inside the inventory panel for remapping."""
        SS  = self.SLOT_SIZE - 4
        PAD = 6
        total_w = self.SLOTS * (SS + PAD) - PAD
        ox = px + (panel_w - total_w) // 2
        oy = py + 42

        label = self._txt("Raccourcis rapides :", self.font_sm, (180, 200, 240))
        self.screen.blit(label, (ox, oy))
        oy += 18

        for i in range(self.SLOTS):
            sx = ox + i * (SS + PAD)
            bg = self._slot_sel if i == self.sel_slot else self._slot_bg
            scaled = pygame.transform.scale(bg, (SS, SS))
            self.screen.blit(scaled, (sx, oy))
            b = self.hotbar[i]
            if b != AIR:
                self.renderer.draw_block_icon(b, pygame.Rect(sx + 4, oy + 4, SS - 8, SS - 8))
            num = self._txt(str(i + 1), self.font_sm, (200, 200, 100))
            self.screen.blit(num, (sx + 2, oy + 2))

    def _draw_inv_grid(self, items: list[int],
                       px: int, py: int, panel_w: int, panel_h: int) -> None:
        SS   = 44
        PAD  =  6
        COLS = (panel_w - 20) // (SS + PAD)
        ox   = px + 10
        oy   = py + 6

        label = self._txt(
            "Blocs collectés" if self._inv_tab == 0 else "Palette créative",
            self.font_sm, (180, 200, 240))
        self.screen.blit(label, (ox, oy))
        oy += 20

        for i, block in enumerate(items):
            r = i // COLS
            c = i  % COLS
            sx = ox + c * (SS + PAD)
            sy = oy + r * (SS + PAD)
            if sy + SS > py + panel_h:
                break

            bg = pygame.Surface((SS, SS), pygame.SRCALPHA)
            bg.fill(C_SLOT_BG)
            pygame.draw.rect(bg, C_SLOT_BORD, bg.get_rect(), 2)
            self.screen.blit(bg, (sx, sy))
            if block != AIR:
                self.renderer.draw_block_icon(block, pygame.Rect(sx + 4, sy + 4, SS - 8, SS - 8))

    # ── Crafting tab ─────────────────────────────────────────────────────────

    def _craft_geo(self) -> dict:
        """Shared geometry for the crafting tab, keyed off current screen size."""
        sw, sh = self.sw, self.sh
        panel_w = min(700, sw - 40)
        panel_h = min(540, sh - 40)
        panel_x = (sw - panel_w) // 2
        panel_y = (sh - panel_h) // 2
        body_top = panel_y + 36
        SS, PAD = 48, 6
        grid_side = 3 * (SS + PAD) - PAD   # 156
        result_ss = 60
        arrow_sp  = 40
        widget_w  = grid_side + arrow_sp + result_ss  # 256
        ox = panel_x + (panel_w - widget_w) // 2
        oy = body_top + 28
        arrow_x = ox + grid_side + 8
        res_x   = arrow_x + arrow_sp
        res_y   = oy + (grid_side - result_ss) // 2
        sep_y   = oy + grid_side + 14
        inv_y   = sep_y + 26
        return dict(panel_x=panel_x, panel_y=panel_y, panel_w=panel_w, panel_h=panel_h,
                    body_top=body_top, SS=SS, PAD=PAD, grid_side=grid_side,
                    result_ss=result_ss, ox=ox, oy=oy,
                    arrow_x=arrow_x, res_x=res_x, res_y=res_y,
                    sep_y=sep_y, inv_y=inv_y)

    def _draw_craft_tab(self, panel_x: int, panel_y: int,
                        panel_w: int, panel_h: int) -> None:
        g = self._craft_geo()
        SS = g["SS"]; PAD = g["PAD"]
        ox = g["ox"]; oy = g["oy"]
        grid_side = g["grid_side"]

        # Grid label
        lbl = self._txt("Grille d'artisanat :", self.font_sm, (180, 200, 240))
        self.screen.blit(lbl, (ox, g["body_top"] + 6))

        # Compute recipe
        grid_2d = [self._craft_grid[r * 3:(r + 1) * 3] for r in range(3)]
        recipe  = match_recipe(grid_2d)

        # 3×3 grid
        for i in range(9):
            r, c = divmod(i, 3)
            sx = ox + c * (SS + PAD)
            sy = oy + r * (SS + PAD)
            bg = pygame.Surface((SS, SS), pygame.SRCALPHA)
            bg.fill(C_SLOT_BG)
            bord = C_SLOT_SEL if self._craft_grid[i] != AIR else C_SLOT_BORD
            pygame.draw.rect(bg, bord, bg.get_rect(), 2)
            self.screen.blit(bg, (sx, sy))
            item = self._craft_grid[i]
            if item != AIR:
                self.renderer.draw_block_icon(
                    item, pygame.Rect(sx + 4, sy + 4, SS - 8, SS - 8))

        # Arrow
        arrow_surf = self._txt("→", self.font_lg, (200, 200, 200))
        self.screen.blit(arrow_surf,
                         (g["arrow_x"],
                          oy + (grid_side - arrow_surf.get_height()) // 2))

        # Result slot
        rs = g["result_ss"]
        rx, ry = g["res_x"], g["res_y"]
        res_bg = pygame.Surface((rs, rs), pygame.SRCALPHA)
        if recipe:
            res_bg.fill((40, 70, 40, 200))
            pygame.draw.rect(res_bg, (80, 200, 80), res_bg.get_rect(), 2)
        else:
            res_bg.fill(C_SLOT_BG)
            pygame.draw.rect(res_bg, C_SLOT_BORD, res_bg.get_rect(), 2)
        self.screen.blit(res_bg, (rx, ry))
        if recipe:
            self.renderer.draw_block_icon(
                recipe.result, pygame.Rect(rx + 5, ry + 5, rs - 10, rs - 10))
            ct = self._txt(f"×{recipe.count}", self.font_sm, (180, 255, 180))
            self.screen.blit(ct, (rx + 4, ry + rs - 16))
            hint = self._txt("Clic pour fabriquer", self.font_sm, (150, 220, 150))
            self.screen.blit(hint, (rx, ry + rs + 4))

        # Separator
        pygame.draw.line(self.screen, (60, 70, 100),
                         (panel_x + 8, g["sep_y"]),
                         (panel_x + panel_w - 8, g["sep_y"]), 1)

        # Inventory items below (click to send to grid)
        lbl2 = self._txt("Matériaux (clic → grille) :", self.font_sm, (180, 200, 240))
        self.screen.blit(lbl2, (panel_x + 10, g["sep_y"] + 6))

        avail_h = (panel_y + panel_h) - g["inv_y"] - 4
        if avail_h > 0:
            self._draw_inv_grid(self.inventory, panel_x, g["inv_y"], panel_w, avail_h)

    # ── Inventory interaction ─────────────────────────────────────────────────

    def inventory_mouse_down(self, pos: tuple[int, int]) -> bool:
        """Handle mousedown inside inventory. Returns True if handled."""
        if not self.show_inventory:
            return False
        sw, sh = self.sw, self.sh
        panel_w, panel_h = min(700, sw - 40), min(540, sh - 40)
        px = (sw - panel_w) // 2
        py = (sh - panel_h) // 2

        # Tab click
        tab_labels = ["Collectés", "Créatif", "Artisanat"]
        tab_w = 100
        for i in range(len(tab_labels)):
            tx = px + panel_w - tab_w * (len(tab_labels) - i) - 8
            ty = py + 2
            if tx <= pos[0] <= tx + tab_w and ty <= pos[1] <= ty + 32:
                self._inv_tab = i
                return True

        # ── Crafting tab interactions ─────────────────────────────────────────
        if self._inv_tab == 2:
            g = self._craft_geo()
            SS = g["SS"]; PAD = g["PAD"]
            ox = g["ox"]; oy = g["oy"]

            # Click on a craft grid slot → clear it
            for i in range(9):
                r, c = divmod(i, 3)
                sx = ox + c * (SS + PAD)
                sy = oy + r * (SS + PAD)
                if sx <= pos[0] <= sx + SS and sy <= pos[1] <= sy + SS:
                    self._craft_grid[i] = AIR
                    return True

            # Click on result slot → craft
            rs = g["result_ss"]
            rx, ry = g["res_x"], g["res_y"]
            if rx <= pos[0] <= rx + rs and ry <= pos[1] <= ry + rs:
                grid_2d = [self._craft_grid[r * 3:(r + 1) * 3] for r in range(3)]
                recipe  = match_recipe(grid_2d)
                if recipe:
                    self.add_item(recipe.result)
                    self._craft_grid = [AIR] * 9
                return True

            # Click on an inventory item below → send to first empty craft slot
            SS2, PAD2 = 44, 6
            COLS = (panel_w - 20) // (SS2 + PAD2)
            gox  = px + 10
            goy  = g["inv_y"] + 6 + 20   # label + offset (matches _draw_inv_grid)
            for i, item in enumerate(self.inventory):
                r, c = divmod(i, COLS)
                sx = gox + c * (SS2 + PAD2)
                sy = goy + r * (SS2 + PAD2)
                if sx <= pos[0] <= sx + SS2 and sy <= pos[1] <= sy + SS2:
                    # Place in first empty craft slot
                    for j in range(9):
                        if self._craft_grid[j] == AIR:
                            self._craft_grid[j] = item
                            break
                    return True

            return True  # absorb all clicks in craft tab

        # ── Normal tabs ───────────────────────────────────────────────────────

        # Hotbar slot inside panel
        SS = self.SLOT_SIZE - 4; PAD = 6
        total_w = self.SLOTS * (SS + PAD) - PAD
        ox = px + (panel_w - total_w) // 2
        oy = py + 42 + 18
        for i in range(self.SLOTS):
            sx = ox + i * (SS + PAD)
            if sx <= pos[0] <= sx + SS and oy <= pos[1] <= oy + SS:
                # Start drag from hotbar
                self._drag_item   = self.hotbar[i]
                self._drag_origin = ("hotbar", i)
                self._drag_pos    = pos
                return True

        # Item grid click → start drag
        SS = 44; PAD = 6
        COLS = (panel_w - 20) // (SS + PAD)
        gox  = px + 10
        goy  = py + 36 + 80 + 6 + 20
        items = self.inventory if self._inv_tab == 0 else CREATIVE_PALETTE
        for i, block in enumerate(items):
            r = i // COLS; c = i % COLS
            sx = gox + c * (SS + PAD)
            sy = goy + r * (SS + PAD)
            if sx <= pos[0] <= sx + SS and sy <= pos[1] <= sy + SS:
                self._drag_item   = block
                self._drag_origin = ("inv", i)
                self._drag_pos    = pos
                return True

        return True   # absorb click inside panel

    def inventory_mouse_up(self, pos: tuple[int, int]) -> None:
        if self._drag_item is None:
            return
        sw, sh = self.sw, self.sh
        panel_w, _ = min(700, sw - 40), min(540, sh - 40)
        px = (sw - panel_w) // 2
        py = (sh - min(540, sh - 40)) // 2

        # Drop onto hotbar slot inside panel?
        SS = self.SLOT_SIZE - 4; PAD = 6
        total_w = self.SLOTS * (SS + PAD) - PAD
        ox = px + (panel_w - total_w) // 2
        oy = py + 42 + 18
        for i in range(self.SLOTS):
            sx = ox + i * (SS + PAD)
            if sx <= pos[0] <= sx + SS and oy <= pos[1] <= oy + SS:
                self.hotbar[i] = self._drag_item
                break

        self._drag_item   = None
        self._drag_origin = None

    def inventory_mouse_move(self, pos: tuple[int, int]) -> None:
        if self._drag_item is not None:
            self._drag_pos = pos

    def add_item(self, block: int) -> None:
        """Add a collected block to the player inventory."""
        if block != AIR and block not in self.inventory:
            self.inventory.append(block)
        # Also auto-fill first empty hotbar slot
        for i, b in enumerate(self.hotbar):
            if b == AIR:
                self.hotbar[i] = block
                return
            if b == block:
                return

    # ── Hotbar (always visible) ───────────────────────────────────────────────

    def _draw_hotbar(self) -> None:
        SS  = self.SLOT_SIZE; PAD = self.SLOT_PAD; n = self.SLOTS
        total_w = n * (SS + PAD) - PAD
        ox = (self.sw - total_w) // 2
        oy = self.sh - SS - 12

        for i, block in enumerate(self.hotbar):
            sx = ox + i * (SS + PAD)
            self.screen.blit(self._slot_sel if i == self.sel_slot else self._slot_bg,
                             (sx, oy))
            if block != AIR:
                self.renderer.draw_block_icon(block,
                    pygame.Rect(sx + 6, oy + 6, SS - 12, SS - 12))
            num = self._txt(str(i + 1), self.font_sm, C_TEXT, shadow=True)
            self.screen.blit(num, (sx + 4, oy + 4))

    # ── Mining bar ───────────────────────────────────────────────────────────

    def _draw_mining_bar(self, player: "Player") -> None:
        if player.mining_target is None or player.mining_progress <= 0:
            return
        bar_w, bar_h = 160, 14
        ox = (self.sw - bar_w) // 2
        oy = self.sh - self.SLOT_SIZE - 12 - bar_h - 8
        bg = pygame.Surface((bar_w + 4, bar_h + 4), pygame.SRCALPHA)
        bg.fill((20, 20, 20, 180))
        self.screen.blit(bg, (ox - 2, oy - 2))
        fill = int(bar_w * player.mining_progress)
        if fill:
            pygame.draw.rect(self.screen, C_MINE_BAR, (ox, oy, fill, bar_h))
        pygame.draw.rect(self.screen, (180, 180, 180), (ox, oy, bar_w, bar_h), 1)

    # ── Clock ─────────────────────────────────────────────────────────────────

    def _draw_clock(self, t: float) -> None:
        cx, cy, r = self.sw - 40, 40, 24
        pygame.draw.circle(self.screen, (30, 30, 30, 180), (cx, cy), r)
        pygame.draw.circle(self.screen, (120, 120, 120), (cx, cy), r, 2)
        angle   = (t - 0.5) * math.tau
        hx = cx + int(r * 0.65 * math.sin(angle))
        hy = cy - int(r * 0.65 * math.cos(angle))
        col = (255, 220, 50) if 0.2 <= t <= 0.8 else (200, 200, 230)
        pygame.draw.circle(self.screen, col, (hx, hy), 8 if 0.2 <= t <= 0.8 else 6)

    def _draw_coords(self, player: "Player") -> None:
        t = self._txt(f"X:{int(player.x)}  Y:{int(player.y)}",
                      self.font_sm, C_TEXT, shadow=True)
        self.screen.blit(t, (8, 8))

    def _draw_tooltip(self, block: int) -> None:
        name = ITEM_NAMES.get(block) or BLOCK_NAMES.get(block, "?")
        t    = self._txt(name, self.font_md, C_TEXT)
        pad  = 8; w = t.get_width() + pad*2; h = t.get_height() + pad*2
        ox   = (self.sw - w) // 2
        oy   = self.sh - self.SLOT_SIZE - 12 - 36 - h - 4
        bg   = pygame.Surface((w, h), pygame.SRCALPHA); bg.fill(C_TOOLTIP_BG)
        self.screen.blit(bg, (ox, oy))
        self.screen.blit(t,  (ox + pad, oy + pad))

    def _draw_hints(self) -> None:
        hint = ("Clic gauche:miner  Clic droit:poser  "
                "E:inventaire  +/-:zoom  1-9/molette:slot")
        s = self._txt(hint, self.font_sm, (200, 200, 200), shadow=True)
        self.screen.blit(s, (self.sw // 2 - s.get_width() // 2,
                             self.sh - self.SLOT_SIZE - 12 - 20))

    # ── Slot graphics ─────────────────────────────────────────────────────────

    def _make_slot(self, selected: bool) -> pygame.Surface:
        SS = self.SLOT_SIZE
        s  = pygame.Surface((SS, SS), pygame.SRCALPHA)
        s.fill(C_SLOT_BG)
        pygame.draw.rect(s, C_SLOT_SEL if selected else C_SLOT_BORD, s.get_rect(), 3)
        if selected:
            g = pygame.Surface((SS, SS), pygame.SRCALPHA); g.fill((255, 200, 50, 25))
            s.blit(g, (0, 0))
        return s

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _txt(self, text: str, font: pygame.font.Font,
             color: tuple, shadow: bool = False) -> pygame.Surface:
        if shadow:
            sh = font.render(text, True, C_SHADOW)
            mn = font.render(text, True, color)
            out = pygame.Surface((mn.get_width()+1, mn.get_height()+1), pygame.SRCALPHA)
            out.blit(sh, (1, 1)); out.blit(mn, (0, 0))
            return out
        return font.render(text, True, color)

    def scroll_slot(self, d: int) -> None:
        self.sel_slot = (self.sel_slot + d) % self.SLOTS

    def select_slot(self, i: int) -> None:
        if 0 <= i < self.SLOTS:
            self.sel_slot = i

    @property
    def selected_block(self) -> int:
        return self.hotbar[self.sel_slot]
