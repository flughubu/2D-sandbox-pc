"""
Tile atlas loading and world rendering.

The original TileMap.png is a 2048×2048 RGBA image containing a 32×32 grid
of 64×64 tiles. We cache each tile as a pygame.Surface scaled to BLOCK_SIZE.
"""
from __future__ import annotations

import os
import math
from functools import lru_cache
from typing import TYPE_CHECKING

import pygame

from tiles import (
    AIR, GRASS, WATER, LAVA, LEAVES,
    BLOCK_ATLAS, TRANSPARENT_BLOCKS,
)

if TYPE_CHECKING:
    from world import World

# ── Layout ───────────────────────────────────────────────────────────────────
BLOCK_SIZE   = 32          # pixels per block on screen
ATLAS_TILE   = 64          # source pixels per tile in atlas
ATLAS_COLS   = 32          # tiles per row in atlas
ATLAS_ROWS   = 32          # tiles per column in atlas
RENDER_DIST  = 2           # extra blocks drawn beyond screen edge

ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "apk_extracted", "assets", "GameResources",
)
ATLAS_PATH = os.path.join(ASSETS_DIR, "HDTex", "TileMap.png")

# ── Colour palette for fallback / unknown blocks ──────────────────────────────
FALLBACK_COLORS: dict[int, tuple[int, int, int]] = {
    AIR:    (0, 0, 0, 0),
}


class Renderer:
    """Loads the tile atlas and exposes a draw_world() method."""

    def __init__(self, screen: pygame.Surface):
        self.screen     = screen
        self.sw, self.sh = screen.get_size()
        self._atlas_raw: pygame.Surface | None = None
        self._tile_cache: dict[int, pygame.Surface] = {}
        self._grass_color = (72, 160, 48)
        self._water_anim  = 0   # frame counter for water ripple
        self._load_atlas()

    # ── Atlas loading ─────────────────────────────────────────────────────────

    def _load_atlas(self) -> None:
        if os.path.exists(ATLAS_PATH):
            raw = pygame.image.load(ATLAS_PATH).convert_alpha()
            self._atlas_raw = raw
        else:
            self._atlas_raw = None

    def _get_tile(self, block_id: int) -> pygame.Surface | None:
        """Return a BLOCK_SIZE×BLOCK_SIZE surface for block_id (cached)."""
        if block_id in self._tile_cache:
            return self._tile_cache[block_id]

        pos = BLOCK_ATLAS.get(block_id)
        if pos is None:
            return None   # AIR or unknown

        if self._atlas_raw is None:
            return None

        col, row = pos
        src_x = col * ATLAS_TILE
        src_y = row * ATLAS_TILE

        # Crop tile from atlas
        try:
            sub = self._atlas_raw.subsurface(
                (src_x, src_y, ATLAS_TILE, ATLAS_TILE)
            )
        except ValueError:
            return None

        # Scale to screen block size
        surf = pygame.transform.scale(sub, (BLOCK_SIZE, BLOCK_SIZE)).convert_alpha()

        # For tiles that are semi-transparent (e.g., water), ensure they have
        # a visible colour base
        if block_id == WATER:
            base = pygame.Surface((BLOCK_SIZE, BLOCK_SIZE), pygame.SRCALPHA)
            base.fill((30, 100, 180, 180))
            base.blit(surf, (0, 0))
            surf = base

        self._tile_cache[block_id] = surf
        return surf

    # ── Main draw method ──────────────────────────────────────────────────────

    def draw_world(self, world: "World", cam_x: float, cam_y: float,
                   time_of_day: float) -> None:
        """
        Draw visible blocks.
        cam_x, cam_y: world-space position of the top-left of the screen (in blocks).
        time_of_day: 0.0=midnight, 0.5=noon, 1.0=midnight again
        """
        self._water_anim = (self._water_anim + 1) % 60
        W = world.width
        BS = BLOCK_SIZE
        sw, sh = self.sw, self.sh

        # Sky background
        sky = self._sky_color(time_of_day)
        self.screen.fill(sky)

        # Visible block range
        col_start = int(cam_x) - RENDER_DIST
        col_end   = int(cam_x + sw / BS) + RENDER_DIST + 1
        row_start = max(0, int(cam_y) - RENDER_DIST)
        row_end   = min(world.height, int(cam_y + sh / BS) + RENDER_DIST + 1)

        ambient = self._ambient(time_of_day)   # 0.0 – 1.0

        for wy in range(row_start, row_end):
            sy = int((wy - cam_y) * BS)
            for wx_raw in range(col_start, col_end):
                wx = wx_raw % W
                block = world.get(wx, wy)
                if block == AIR:
                    continue

                sx = int((wx_raw - cam_x) * BS)

                # Wrap-around: draw block on left AND right side if needed
                surf = self._get_tile(block)
                self._draw_block(surf, block, sx, sy, wx, wy, world, ambient)

        # Lighting overlay (dim screen at night)
        if ambient < 1.0:
            darkness = int((1.0 - ambient) * 180)
            overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
            overlay.fill((0, 0, 20, darkness))
            self.screen.blit(overlay, (0, 0))

    def _draw_block(self, surf: pygame.Surface | None, block: int,
                    sx: int, sy: int,
                    wx: int, wy: int, world: "World",
                    ambient: float) -> None:
        BS = BLOCK_SIZE
        rect = pygame.Rect(sx, sy, BS, BS)

        if surf is not None:
            self.screen.blit(surf, rect)
        else:
            # Fallback solid colour
            color = FALLBACK_COLORS.get(block, (150, 150, 150))
            if len(color) == 4 and color[3] == 0:
                return
            pygame.draw.rect(self.screen, color[:3], rect)

        # Grass top-strip overlay
        if block == GRASS:
            above = world.get(wx, wy - 1)
            if above == AIR:
                strip = pygame.Rect(sx, sy, BS, 5)
                gs = pygame.Surface((BS, 5), pygame.SRCALPHA)
                gs.fill((*self._grass_color, 200))
                self.screen.blit(gs, strip)

        # Water shimmer
        if block == WATER:
            phase = (self._water_anim + wx * 7 + wy * 3) % 60
            if phase < 30:
                alpha = int(phase / 30 * 40)
            else:
                alpha = int((60 - phase) / 30 * 40)
            s = pygame.Surface((BS, BS), pygame.SRCALPHA)
            s.fill((180, 220, 255, alpha))
            self.screen.blit(s, rect)

    # ── Sky colour ────────────────────────────────────────────────────────────

    @staticmethod
    def _sky_color(t: float) -> tuple[int, int, int]:
        """Return sky RGB for a time in [0, 1) (0=midnight, 0.5=noon)."""
        # Key colours at various times
        #   0.00 midnight  → very dark blue
        #   0.20 dawn      → orange-pink
        #   0.30 morning   → light blue
        #   0.50 noon      → bright sky blue
        #   0.70 afternoon → warm blue
        #   0.80 dusk      → orange-red
        #   1.00 midnight  → very dark blue
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
            t0, c0 = key[i]
            t1, c1 = key[i + 1]
            if t0 <= t <= t1:
                f = (t - t0) / (t1 - t0)
                return tuple(int(a + (b - a) * f) for a, b in zip(c0, c1))
        return key[0][1]

    @staticmethod
    def _ambient(t: float) -> float:
        """Ambient light factor 0–1 based on time of day."""
        # Noon = 1.0, midnight = 0.15
        # sine-ish curve centred on noon (t=0.5)
        sin_val = math.sin(math.pi * t)   # 0 at 0/1, 1 at 0.5
        return max(0.15, min(1.0, 0.15 + 0.85 * sin_val))

    # ── Utility ───────────────────────────────────────────────────────────────

    def resize(self, width: int, height: int) -> None:
        self.sw, self.sh = width, height

    def draw_block_icon(self, block_id: int, rect: pygame.Rect,
                        screen: pygame.Surface | None = None) -> None:
        """Draw a miniature block icon into rect (used by the HUD)."""
        target = screen or self.screen
        surf = self._get_tile(block_id)
        if surf is not None:
            scaled = pygame.transform.scale(surf, (rect.width, rect.height))
            target.blit(scaled, rect)
        else:
            color = FALLBACK_COLORS.get(block_id, (150, 150, 150))
            pygame.draw.rect(target, color[:3], rect)
