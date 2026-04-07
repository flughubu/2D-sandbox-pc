"""
World data, procedural generation, and block operations.
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import numpy as np

from tiles import (
    AIR, STONE, DIRT, GRASS, SAND, WATER, GRAVEL, LAVA,
    WOOD, LEAVES, COAL_ORE, IRON_ORE, GOLD_ORE,
    LIMESTONE, MARBLE, SNOW, ICE, FLINT,
    SOLID_BLOCKS, LIQUID_BLOCKS, TRANSPARENT_BLOCKS, BLOCK_HARDNESS,
)

# ── World constants ────────────────────────────────────────────────────────
WORLD_WIDTH  = 800   # blocks (wraps horizontally like the original)
WORLD_HEIGHT = 200   # blocks
SEA_LEVEL    = 80    # row index (from top) where water starts


class World:
    """Holds the 2-D block grid and provides generation / mutation helpers."""

    def __init__(self, seed: int | None = None):
        self.width  = WORLD_WIDTH
        self.height = WORLD_HEIGHT
        self.seed   = seed if seed is not None else random.randint(0, 0xFFFF_FFFF)
        self.rng    = random.Random(self.seed)
        # Grid: dtype int8 is enough for ~127 block types; use int16 for safety
        self.grid   = np.zeros((self.height, self.width), dtype=np.int16)
        self._generate()

    # ── Public helpers ────────────────────────────────────────────────────

    def get(self, x: int, y: int) -> int:
        """Return block type at (x, y); wraps horizontally, clamps vertically."""
        if y < 0 or y >= self.height:
            return AIR
        return int(self.grid[y, x % self.width])

    def set(self, x: int, y: int, block: int) -> None:
        """Set block at (x, y), wrapping x."""
        if 0 <= y < self.height:
            self.grid[y, x % self.width] = block

    def is_solid(self, x: int, y: int) -> bool:
        return self.get(x, y) in SOLID_BLOCKS

    def is_passable(self, x: int, y: int) -> bool:
        b = self.get(x, y)
        return b not in SOLID_BLOCKS

    def is_liquid(self, x: int, y: int) -> bool:
        return self.get(x, y) in LIQUID_BLOCKS

    def surface_y(self, x: int) -> int:
        """Return the y of the topmost solid block at column x."""
        for y in range(self.height):
            if self.get(x, y) in SOLID_BLOCKS:
                return y
        return self.height - 1

    # ── Generation ────────────────────────────────────────────────────────

    def _generate(self) -> None:
        rng = self.rng
        W, H = self.width, self.height

        # 1. Height map ---------------------------------------------------
        heights = self._make_heightmap(W, rng)

        # 2. Fill blocks --------------------------------------------------
        grid = self.grid
        for x in range(W):
            ground = heights[x]
            for y in range(H):
                if y < ground:
                    grid[y, x] = AIR
                elif y == ground:
                    if ground >= SEA_LEVEL - 2:
                        grid[y, x] = SAND   # beach / below sea level
                    else:
                        grid[y, x] = GRASS
                elif y <= ground + rng.randint(4, 8):
                    grid[y, x] = DIRT
                elif y <= ground + 40:
                    grid[y, x] = STONE
                elif y <= ground + 80:
                    grid[y, x] = LIMESTONE
                else:
                    grid[y, x] = MARBLE

        # 3. Fill ocean ---------------------------------------------------
        for x in range(W):
            for y in range(H):
                if grid[y, x] == AIR and y >= SEA_LEVEL:
                    grid[y, x] = WATER

        # 4. Caves --------------------------------------------------------
        self._carve_caves(grid, heights, rng)

        # 5. Ores ---------------------------------------------------------
        self._place_ores(grid, heights, rng)

        # 6. Gravel patches -----------------------------------------------
        self._place_gravel(grid, heights, rng)

        # 7. Snow / ice at poles ------------------------------------------
        self._place_poles(grid, heights, rng)

        # 8. Trees --------------------------------------------------------
        self._plant_trees(grid, heights, rng)

        # 9. Sand dunes ---------------------------------------------------
        self._desert_patches(grid, heights, rng)

        self.grid = grid
        self._heights = heights  # cache for quick lookups

    # ── Heightmap helpers ─────────────────────────────────────────────────

    @staticmethod
    def _make_heightmap(W: int, rng: random.Random) -> list[int]:
        """Multi-octave sine-based heightmap, clamped to valid range."""
        offsets = [rng.uniform(0, math.tau) for _ in range(6)]
        freqs   = [0.006, 0.015, 0.04, 0.09, 0.2, 0.5]
        amps    = [12.0,  7.0,   4.0,  2.5,  1.5, 0.8]
        base    = SEA_LEVEL - 10  # average surface above sea

        raw = []
        for x in range(W):
            h = base + sum(
                a * math.sin(x * f + o)
                for a, f, o in zip(amps, freqs, offsets)
            )
            raw.append(int(h))

        # Smooth with a simple moving average
        k = 5
        heights = []
        for x in range(W):
            s = sum(raw[max(0, x - k): x + k + 1])
            n = min(x + k + 1, W) - max(0, x - k)
            heights.append(max(30, min(WORLD_HEIGHT - 20, s // n)))

        # Inject a few mountains and valleys
        for _ in range(W // 60):
            cx = rng.randint(50, W - 50)
            delta = rng.choice([-1, 1]) * rng.randint(8, 20)
            w = rng.randint(20, 50)
            for dx in range(-w, w + 1):
                xx = (cx + dx) % W
                factor = 1.0 - abs(dx) / w
                heights[xx] = max(30, min(WORLD_HEIGHT - 20,
                                          heights[xx] + int(delta * factor)))

        return heights

    # ── Cave carving ─────────────────────────────────────────────────────

    def _carve_caves(self, grid: np.ndarray, heights: list[int],
                     rng: random.Random) -> None:
        W, H = self.width, self.height
        n_tunnels = W // 6
        for _ in range(n_tunnels):
            x = rng.randint(0, W - 1)
            y = rng.randint(heights[x] + 10, min(H - 5, heights[x] + 120))
            length = rng.randint(20, 80)
            r = rng.randint(2, 4)
            dx = rng.uniform(-1.5, 1.5)
            dy = rng.uniform(-0.5, 0.5)
            for _ in range(length):
                # Carve a small oval
                for cy in range(-r, r + 1):
                    for cx in range(-r, r + 1):
                        if cx * cx + cy * cy * 2 <= r * r * 2:
                            ny, nx = y + cy, (x + cx) % W
                            if 0 < ny < H - 1 and grid[ny, nx] not in (AIR, WATER, LAVA):
                                grid[ny, nx] = AIR
                x = int(x + dx) % W
                y = int(y + dy)
                y = max(heights[x] + 8, min(H - 5, y))
                dx += rng.uniform(-0.3, 0.3)
                dy += rng.uniform(-0.15, 0.15)
                dx = max(-2.0, min(2.0, dx))
                dy = max(-0.8, min(0.8, dy))

    # ── Ore placement ────────────────────────────────────────────────────

    def _place_ores(self, grid: np.ndarray, heights: list[int],
                    rng: random.Random) -> None:
        W, H = self.width, self.height
        ore_specs = [
            # (type,      vein_size, n_veins, min_depth, max_depth)
            (COAL_ORE,   5,  W // 15, 5,  60),
            (FLINT,      4,  W // 20, 3,  30),
            (IRON_ORE,   4,  W // 20, 15, 90),
            (GOLD_ORE,   3,  W // 30, 40, 130),
        ]
        for ore, size, count, dmin, dmax in ore_specs:
            for _ in range(count):
                cx = rng.randint(0, W - 1)
                surface = heights[cx]
                cy = surface + rng.randint(dmin, min(dmax, H - surface - 5))
                if cy >= H:
                    continue
                for _ in range(size):
                    nx, ny = cx + rng.randint(-2, 2), cy + rng.randint(-2, 2)
                    nx %= W
                    if 0 <= ny < H and grid[ny, nx] in (STONE, LIMESTONE, MARBLE):
                        grid[ny, nx] = ore

    # ── Gravel patches ────────────────────────────────────────────────────

    def _place_gravel(self, grid: np.ndarray, heights: list[int],
                      rng: random.Random) -> None:
        W = self.width
        for _ in range(W // 25):
            cx = rng.randint(0, W - 1)
            surface = heights[cx]
            cy = surface + rng.randint(2, 25)
            for dy in range(-2, 3):
                for dx in range(-3, 4):
                    nx, ny = (cx + dx) % W, cy + dy
                    if 0 <= ny < self.height and grid[ny, nx] in (STONE, DIRT):
                        grid[ny, nx] = GRAVEL

    # ── Poles ────────────────────────────────────────────────────────────

    def _place_poles(self, grid: np.ndarray, heights: list[int],
                     rng: random.Random) -> None:
        W = self.width
        pole_width = W // 16          # narrower poles
        for pole_cx in (W // 4, 3 * W // 4):
            for x in range(pole_cx - pole_width, pole_cx + pole_width):
                xx = x % W
                y = heights[xx]
                dist = abs(x - pole_cx) / pole_width
                # Snow on surface
                if 0 <= y < self.height and grid[y, xx] in (GRASS, DIRT, STONE, SAND):
                    grid[y, xx] = SNOW
                # Ice replaces water
                if 0 <= y + 1 < self.height and grid[y + 1, xx] == WATER:
                    grid[y + 1, xx] = ICE

    # ── Trees ─────────────────────────────────────────────────────────────

    def _plant_trees(self, grid: np.ndarray, heights: list[int],
                     rng: random.Random) -> None:
        W, H = self.width, self.height
        x = 10
        while x < W - 10:
            surface = heights[x]
            block_at = grid[surface, x]
            if block_at == GRASS and rng.random() < 0.15:
                trunk_h = rng.randint(4, 8)
                # Trunk
                for ty in range(surface - trunk_h, surface):
                    if 0 <= ty < H:
                        grid[ty, x] = WOOD
                # Canopy
                canopy_y = surface - trunk_h
                leaf_r = rng.randint(3, 4)
                for ly in range(-leaf_r, 3):
                    for lx in range(-leaf_r, leaf_r + 1):
                        if lx * lx + ly * ly * 1.2 <= leaf_r * leaf_r * 1.2:
                            ny = canopy_y + ly
                            nx = (x + lx) % W
                            if 0 <= ny < H and grid[ny, nx] == AIR:
                                if rng.random() > 0.15:
                                    grid[ny, nx] = LEAVES
                x += rng.randint(6, 15)
            else:
                x += rng.randint(2, 6)

    # ── Desert patches ────────────────────────────────────────────────────

    def _desert_patches(self, grid: np.ndarray, heights: list[int],
                        rng: random.Random) -> None:
        W = self.width
        for _ in range(W // 150):      # fewer desert patches
            cx = rng.randint(0, W - 1)
            width = rng.randint(20, 60)
            for dx in range(-width, width + 1):
                xx = (cx + dx) % W
                y = heights[xx]
                depth = rng.randint(2, 5)
                for dy in range(depth):
                    ny = y + dy
                    if 0 <= ny < self.height and grid[ny, xx] in (GRASS, DIRT, GRAVEL):
                        grid[ny, xx] = SAND
