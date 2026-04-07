"""
Lighting and fog-of-war system.

Light map  : numpy float32 array [0..1] per block, updated each frame.
Fog map    : numpy bool array  – True = block has been seen at least once.

Light sources
-------------
- Sky        : surface blocks + blocks above the heightmap get full daylight
               (modulated by time_of_day).
- Torches    : radius ~6, intensity 1.0
- Player     : tiny personal glow, radius 3, intensity 0.35
- Lava       : radius 4, intensity 0.8

Underground default: 0.0 (pitch black).
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from world import World

# Block types that emit light  →  (radius, intensity 0-1)
from tiles import LAVA, WATER   # imported lazily to avoid circular deps

LIGHT_EMITTERS: dict[int, tuple[int, float]] = {}   # filled by init()

# How many blocks around the player to keep the fog revealed
FOG_REVEAL_RADIUS = 20

# Minimum light level even in pitch-black caves (so it's not 100% invisible)
AMBIENT_CAVE = 0.0


def _init_emitters() -> None:
    """Populate LIGHT_EMITTERS after tiles module is ready."""
    from tiles import LAVA as _LAVA
    LIGHT_EMITTERS[_LAVA] = (4, 0.80)
    # TORCH handled via TORCH_BLOCK constant set by tiles


_init_emitters()


class LightingSystem:
    """Manages the light map and fog of war for the world."""

    def __init__(self, world: "World"):
        H, W = world.height, world.width
        self.world = world

        # Light level per block, 0.0 – 1.0
        self.light: np.ndarray = np.zeros((H, W), dtype=np.float32)

        # Fog of war: True = player has seen this cell
        self.fog: np.ndarray = np.zeros((H, W), dtype=bool)

        # Cache surface heights (for sky light)
        self._surface = np.array(world._heights, dtype=np.int32)

        # Dirty flag – rebuild full light map on first call
        self._dirty = True

    # ── Public API ─────────────────────────────────────────────────────────

    def update(self, player_bx: int, player_by: int,
               time_of_day: float, zoom_radius: int = 30) -> None:
        """
        Recalculate light in the visible+nearby region.
        Called once per frame (fast: only processes visible window).
        """
        world = self.world
        H, W  = world.height, world.width

        sky_strength = self._sky_light(time_of_day)

        # Window to update  (player-centred, capped to world bounds)
        r = zoom_radius + 4
        x0 = max(0, player_bx - r)
        x1 = min(W, player_bx + r + 1)
        y0 = max(0, player_by - r)
        y1 = min(H, player_by + r + 1)

        # --- Sky light pass ---
        for bx in range(x0, x1):
            surf_y = int(self._surface[bx])
            for by in range(y0, y1):
                if by <= surf_y:
                    # Above or at surface → full sky light
                    self.light[by, bx] = sky_strength
                else:
                    self.light[by, bx] = AMBIENT_CAVE

        # --- Block emitters ---
        for by in range(y0, y1):
            for bx in range(x0, x1):
                block = world.get(bx, by)
                if block in LIGHT_EMITTERS:
                    radius, intensity = LIGHT_EMITTERS[block]
                    self._spread_light(bx, by, radius, intensity, x0, x1, y0, y1)

        # --- Torch emitters (dynamic, from a separate pass) ---
        from tiles import TORCH_BLOCK
        for by in range(y0, y1):
            for bx in range(x0, x1):
                if world.get(bx, by) == TORCH_BLOCK:
                    self._spread_light(bx, by, 7, 1.0, x0, x1, y0, y1)

        # --- Player personal glow ---
        self._spread_light(player_bx, player_by, 3, 0.35, x0, x1, y0, y1)

        # --- Fog of war reveal ---
        self._reveal_fog(player_bx, player_by, FOG_REVEAL_RADIUS, H, W)

    def _spread_light(self, cx: int, cy: int,
                      radius: int, intensity: float,
                      x0: int, x1: int, y0: int, y1: int) -> None:
        """Add point-light contribution within the update window."""
        H, W = self.light.shape
        r2 = radius * radius
        for dy in range(-radius, radius + 1):
            by = cy + dy
            if not (y0 <= by < y1):
                continue
            for dx in range(-radius, radius + 1):
                bx = (cx + dx) % W
                if not (x0 <= bx < x1):
                    continue
                dist2 = dx * dx + dy * dy
                if dist2 > r2:
                    continue
                # Linear fall-off
                contrib = intensity * (1.0 - math.sqrt(dist2) / radius)
                if contrib > self.light[by, bx]:
                    self.light[by, bx] = contrib

    def _reveal_fog(self, px: int, py: int,
                    radius: int, H: int, W: int) -> None:
        r2 = radius * radius
        for dy in range(-radius, radius + 1):
            by = py + dy
            if not (0 <= by < H):
                continue
            for dx in range(-radius, radius + 1):
                bx = (px + dx) % W
                dist2 = dx * dx + dy * dy
                if dist2 <= r2:
                    self.fog[by, bx] = True

    @staticmethod
    def _sky_light(t: float) -> float:
        """Sky light strength 0–1 based on time of day."""
        # Same curve as renderer ambient
        s = math.sin(math.pi * t)
        return max(0.05, min(1.0, 0.1 + 0.9 * s))
