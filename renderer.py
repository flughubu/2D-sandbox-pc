"""
Tile atlas loading, world rendering, lighting overlay, fog of war.
"""
from __future__ import annotations

import math
import os
from typing import TYPE_CHECKING

import numpy as np
import pygame

from tiles import AIR, GRASS, WATER, LAVA, TORCH_BLOCK, BLOCK_ATLAS

if TYPE_CHECKING:
    from world   import World
    from lighting import LightingSystem

# ── Layout ────────────────────────────────────────────────────────────────────
BLOCK_SIZE_DEFAULT = 32
BLOCK_SIZE_MIN     = 12
BLOCK_SIZE_MAX     = 64
ATLAS_TILE         = 64
ATLAS_COLS         = 32
RENDER_PAD         = 2   # extra blocks drawn beyond screen edge

ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "apk_extracted", "assets", "GameResources",
)
ATLAS_PATH = os.path.join(ASSETS_DIR, "HDTex", "TileMap.png")

FALLBACK_COLORS: dict[int, tuple] = {
    # Crafted / non-placeable items (IDs 100+)
    100: (160, 100,  40),  # Stick
    101: (210, 160,  80),  # Wood Plank
    102: ( 70,  70,  90),  # Flint Knife
    103: ( 70,  70,  90),  # Flint Spade
    104: ( 70,  70,  90),  # Flint Pick
    105: ( 25,  25,  25),  # Coal
    106: (180, 185, 200),  # Iron Ingot
    107: (225, 185,  30),  # Gold Ingot
    108: (220, 100,  30),  # Campfire
    109: (130,  85,  45),  # Workbench
    110: (130, 155, 175),  # Iron Pick
    111: (130, 155, 175),  # Iron Sword
    112: (130, 155, 175),  # Iron Spade
    113: (200, 160,  30),  # Gold Pick
    114: (210, 170,  80),  # Bread
    115: (220, 220, 220),  # String
}
GRASS_COLOR = (72, 160, 48)


class Renderer:
    def __init__(self, screen: pygame.Surface):
        self.screen     = screen
        self.sw, self.sh = screen.get_size()
        self.block_size  = BLOCK_SIZE_DEFAULT   # current zoom level (px/block)
        self._atlas_raw: pygame.Surface | None = None
        self._tile_cache: dict[tuple[int, int], pygame.Surface] = {}  # size→tile cache
        self._water_anim = 0
        self._load_atlas()

    # ── Atlas ─────────────────────────────────────────────────────────────────

    def _load_atlas(self) -> None:
        if os.path.exists(ATLAS_PATH):
            self._atlas_raw = pygame.image.load(ATLAS_PATH).convert_alpha()

    def _get_tile(self, block_id: int) -> pygame.Surface | None:
        pos = BLOCK_ATLAS.get(block_id)
        if pos is None:
            return None
        key = (block_id, self.block_size)
        if key in self._tile_cache:
            return self._tile_cache[key]
        if self._atlas_raw is None:
            return None
        col, row = pos
        try:
            sub = self._atlas_raw.subsurface(
                (col * ATLAS_TILE, row * ATLAS_TILE, ATLAS_TILE, ATLAS_TILE)
            )
        except ValueError:
            return None
        BS   = self.block_size
        surf = pygame.transform.scale(sub, (BS, BS)).convert_alpha()
        if block_id == WATER:
            base = pygame.Surface((BS, BS), pygame.SRCALPHA)
            base.fill((30, 100, 180, 180))
            base.blit(surf, (0, 0))
            surf = base
        self._tile_cache[key] = surf
        return surf

    # ── Zoom ──────────────────────────────────────────────────────────────────

    def zoom(self, delta: int) -> None:
        """delta: +1 zoom in, -1 zoom out."""
        steps = [12, 16, 20, 24, 28, 32, 40, 48, 56, 64]
        try:
            idx = steps.index(min(steps, key=lambda s: abs(s - self.block_size)))
        except ValueError:
            idx = steps.index(32)
        idx = max(0, min(len(steps) - 1, idx + delta))
        self.block_size = steps[idx]

    # ── Main draw ─────────────────────────────────────────────────────────────

    def draw_world(self, world: "World", cam_x: float, cam_y: float,
                   time_of_day: float,
                   lighting: "LightingSystem | None" = None) -> None:
        self._water_anim = (self._water_anim + 1) % 60
        BS = self.block_size
        W  = world.width
        sw, sh = self.sw, self.sh

        sky = self._sky_color(time_of_day)
        self.screen.fill(sky)

        col_start = int(cam_x) - RENDER_PAD
        col_end   = int(cam_x + sw / BS) + RENDER_PAD + 1
        row_start = max(0, int(cam_y) - RENDER_PAD)
        row_end   = min(world.height, int(cam_y + sh / BS) + RENDER_PAD + 1)

        for wy in range(row_start, row_end):
            sy = int((wy - cam_y) * BS)
            for wx_raw in range(col_start, col_end):
                wx = wx_raw % W
                block = world.get(wx, wy)
                if block == AIR:
                    continue

                sx = int((wx_raw - cam_x) * BS)

                # Fog of war: only draw if player has visited
                if lighting is not None and not lighting.fog[wy, wx]:
                    pygame.draw.rect(self.screen, (0, 0, 0),
                                     (sx, sy, BS, BS))
                    continue

                surf = self._get_tile(block)
                self._draw_block(surf, block, sx, sy, wx, wy, world)

        # Lighting overlay
        if lighting is not None:
            self._draw_lighting(lighting, cam_x, cam_y, world, col_start, col_end,
                                row_start, row_end)

        # Global night dimming (sky only, not underground)
        ambient = self._ambient(time_of_day)
        if ambient < 1.0:
            darkness = int((1.0 - ambient) * 140)
            ov = pygame.Surface((sw, sh), pygame.SRCALPHA)
            ov.fill((0, 0, 20, darkness))
            self.screen.blit(ov, (0, 0))

    def _draw_block(self, surf, block: int,
                    sx: int, sy: int, wx: int, wy: int,
                    world: "World") -> None:
        BS   = self.block_size
        rect = pygame.Rect(sx, sy, BS, BS)
        if surf:
            self.screen.blit(surf, rect)
        else:
            col = FALLBACK_COLORS.get(block, (150, 150, 150))
            if len(col) == 4 and col[3] == 0:
                return
            pygame.draw.rect(self.screen, col[:3], rect)

        # Grass top strip
        if block == GRASS and world.get(wx, wy - 1) == AIR:
            gs = pygame.Surface((BS, max(3, BS // 8)), pygame.SRCALPHA)
            gs.fill((*GRASS_COLOR, 200))
            self.screen.blit(gs, (sx, sy))

        # Water shimmer
        if block == WATER:
            phase = (self._water_anim + wx * 7 + wy * 3) % 60
            alpha = int((30 - abs(phase - 30)) / 30 * 40)
            s = pygame.Surface((BS, BS), pygame.SRCALPHA)
            s.fill((180, 220, 255, alpha))
            self.screen.blit(s, rect)

        # Torch glow hint
        if block == TORCH_BLOCK:
            glow = pygame.Surface((BS, BS), pygame.SRCALPHA)
            pygame.draw.circle(glow, (255, 200, 50, 60), (BS // 2, BS // 2), BS // 2)
            self.screen.blit(glow, rect)

    # ── Lighting overlay ──────────────────────────────────────────────────────

    def _draw_lighting(self, lighting: "LightingSystem",
                       cam_x: float, cam_y: float, world: "World",
                       col_start: int, col_end: int,
                       row_start: int, row_end: int) -> None:
        BS = self.block_size
        W  = world.width

        for wy in range(row_start, row_end):
            sy = int((wy - cam_y) * BS)
            for wx_raw in range(col_start, col_end):
                wx  = wx_raw % W
                if not lighting.fog[wy, wx]:
                    continue
                lv  = float(lighting.light[wy, wx])
                if lv >= 1.0:
                    continue
                # Darkness overlay: 255 at lv=0, 0 at lv=1
                alpha = int((1.0 - lv) * 220)
                if alpha <= 0:
                    continue
                sx = int((wx_raw - cam_x) * BS)
                ov = pygame.Surface((BS, BS), pygame.SRCALPHA)
                ov.fill((0, 0, 10, alpha))
                self.screen.blit(ov, (sx, sy))

    # ── Sky colour ────────────────────────────────────────────────────────────

    @staticmethod
    def _sky_color(t: float) -> tuple[int, int, int]:
        key = [
            (0.00, (10,  15,  40)),
            (0.20, (210, 120,  60)),
            (0.30, (135, 190, 240)),
            (0.50, ( 90, 160, 235)),
            (0.70, (110, 175, 240)),
            (0.80, (220,  80,  30)),
            (1.00, ( 10,  15,  40)),
        ]
        for i in range(len(key) - 1):
            t0, c0 = key[i]; t1, c1 = key[i + 1]
            if t0 <= t <= t1:
                f = (t - t0) / (t1 - t0)
                return tuple(int(a + (b - a) * f) for a, b in zip(c0, c1))
        return key[0][1]

    @staticmethod
    def _ambient(t: float) -> float:
        return max(0.15, min(1.0, 0.15 + 0.85 * math.sin(math.pi * t)))

    # ── Utilities ─────────────────────────────────────────────────────────────

    def resize(self, w: int, h: int) -> None:
        self.sw, self.sh = w, h

    def draw_block_icon(self, block_id: int, rect: pygame.Rect,
                        target: pygame.Surface | None = None) -> None:
        dst   = target or self.screen
        saved = self.block_size
        self.block_size = rect.width
        surf  = self._get_tile(block_id)
        self.block_size = saved
        if surf:
            scaled = pygame.transform.scale(surf, (rect.width, rect.height))
            dst.blit(scaled, rect)
        else:
            col = FALLBACK_COLORS.get(block_id, (150, 150, 150))
            pygame.draw.rect(dst, col[:3], rect)
