"""
Player entity: physics, pathfinding movement, character rendering.
"""
from __future__ import annotations

import os
import math
from typing import TYPE_CHECKING

import pygame

from tiles import SOLID_BLOCKS, LIQUID_BLOCKS, LADDER, AIR

if TYPE_CHECKING:
    from world import World

# ── Physics constants ────────────────────────────────────────────────────────
GRAVITY       =  0.45   # blocks / frame²
# 1-block jump: h = v²/(2g) → v = sqrt(2 * 0.45 * 1) ≈ 0.95
JUMP_FORCE    = -0.95   # blocks / frame  (negative = upward)
MAX_FALL      =  14.0
WALK_SPEED    =  4.5    # blocks / second
LIQUID_SPEED  =  2.5
LIQUID_JUMP   = -0.5
FRICTION      =  0.80
AIR_FRICTION  =  0.92
FPS           =  60

BLOCK_SIZE    = 32      # updated by renderer at runtime

ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "apk_extracted", "assets", "GameResources",
)
SKINS_DIR = os.path.join(ASSETS_DIR, "skins")


class Player:
    """2-D physics entity representing the player's blockhead."""

    WIDTH  = 0.75
    HEIGHT = 1.80

    def __init__(self, world: "World", x: float, y: float):
        self.world = world
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.in_liquid = False
        self.facing    = 1   # 1=right, -1=left

        # Pathfinding
        self.path: list[tuple[int, int]] = []   # remaining waypoints
        self.path_action: str | None = None      # "mine" | "place" | None
        self.path_target: tuple[int, int] | None = None   # block to act on
        self.path_place_block: int = AIR         # block type to place

        # Mining state
        self.mining_target:   tuple[int, int] | None = None
        self.mining_progress: float = 0.0
        self.mining_total:    int   = 0

        # Sprite
        self._sprite:      pygame.Surface | None = None
        self._sprite_left: pygame.Surface | None = None
        self._load_sprites()

    # ── Pathfinding movement ─────────────────────────────────────────────────

    def set_path(self, path: list[tuple[int, int]],
                 action: str, target: tuple[int, int],
                 place_block: int = AIR) -> None:
        self.path         = path
        self.path_action  = action
        self.path_target  = target
        self.path_place_block = place_block
        self.cancel_mining()

    def clear_path(self) -> None:
        self.path        = []
        self.path_action = None
        self.path_target = None

    def _follow_path(self) -> bool:
        """
        Move one step along the path.
        Returns True when the destination waypoint is reached.
        """
        if not self.path:
            return True

        wx, wy = self.path[0]
        W      = self.world.width

        # Current integer foot position
        fx = int(self.x + self.WIDTH / 2) % W
        fy = int(self.y + self.HEIGHT - 0.01)

        # Arrived at this waypoint?
        if fx == wx % W and abs(self.y + self.HEIGHT - 0.01 - wy) < 0.8:
            self.path.pop(0)
            if not self.path:
                return True
            wx, wy = self.path[0]

        # Move horizontally toward waypoint
        dx = (wx - fx + W // 2) % W - W // 2   # shortest horizontal distance
        if abs(dx) > 0.4:
            self.vx = math.copysign(WALK_SPEED / FPS, dx)
            self.facing = 1 if dx > 0 else -1

        # Jump if the waypoint is above us and we are on the ground
        if wy < fy - 0.5 and self.on_ground and self.vy >= 0:
            self.vy = JUMP_FORCE

        return False

    # ── Physics update ───────────────────────────────────────────────────────

    def update(self, keys: pygame.key.ScancodeWrapper, dt: float) -> None:
        frames = dt * FPS

        in_liquid = self.world.is_liquid(
            int(self.x + self.WIDTH / 2),
            int(self.y + self.HEIGHT * 0.6),
        )
        self.in_liquid = in_liquid

        # Path-following overrides manual input
        path_done = False
        if self.path:
            path_done = self._follow_path()
        else:
            # Manual keyboard control
            move_x = 0.0
            speed  = LIQUID_SPEED if in_liquid else WALK_SPEED
            if keys[pygame.K_LEFT]  or keys[pygame.K_a]: move_x -= speed / FPS; self.facing = -1
            if keys[pygame.K_RIGHT] or keys[pygame.K_d]: move_x += speed / FPS; self.facing =  1
            self.vx = move_x if move_x else self.vx * (FRICTION if self.on_ground else AIR_FRICTION)

            if in_liquid:
                self.vy *= 0.85
                if keys[pygame.K_SPACE] or keys[pygame.K_UP] or keys[pygame.K_w]:
                    self.vy += LIQUID_JUMP * 0.08
            else:
                self.vy += GRAVITY * frames
                self.vy = min(self.vy, MAX_FALL)
                if self.on_ground and (
                    keys[pygame.K_SPACE] or keys[pygame.K_UP] or keys[pygame.K_w]
                ):
                    self.vy = JUMP_FORCE

        # Gravity when path-following
        if self.path:
            if in_liquid:
                self.vy *= 0.85
            else:
                self.vy += GRAVITY * frames
                self.vy = min(self.vy, MAX_FALL)

        self._move(self.vx, self.vy * frames)

        # When path finished, perform the queued action
        if path_done and self.path_action and self.path_target:
            self._do_path_action()

    def _do_path_action(self) -> None:
        action = self.path_action
        target = self.path_target
        self.clear_path()
        if action == "mine" and target:
            # Emit a custom event so game.py handles the actual block removal
            pygame.event.post(pygame.event.Event(
                pygame.USEREVENT,
                {"subtype": "mine_reached", "pos": target},
            ))
        elif action == "place" and target:
            pygame.event.post(pygame.event.Event(
                pygame.USEREVENT,
                {"subtype": "place_reached",
                 "pos": target,
                 "block": self.path_place_block},
            ))

    def _move(self, dx: float, dy: float) -> None:
        W = self.world.width
        nx = self.x + dx
        if not self._collides(nx, self.y):
            self.x = nx % W
        else:
            if not self._collides(nx, self.y - 1.0):
                self.x = nx % W
                self.y -= 1.0
            self.vx = 0.0

        ny = self.y + dy
        if not self._collides(self.x, ny):
            self.y = ny
            self.on_ground = False
        else:
            self.on_ground = dy > 0
            self.vy = 0.0

    def _collides(self, px: float, py: float) -> bool:
        world = self.world
        W     = world.width
        left   = int(px)
        right  = int(px + self.WIDTH - 0.01)
        top    = int(py)
        bottom = int(py + self.HEIGHT - 0.01)
        for bx in range(left, right + 1):
            for by in range(top, bottom + 1):
                if world.is_solid(bx % W, by):
                    return True
        return False

    # ── Mining ───────────────────────────────────────────────────────────────

    def start_mining(self, bx: int, by: int, hardness: int) -> None:
        if (bx, by) != self.mining_target:
            self.mining_target   = (bx, by)
            self.mining_progress = 0.0
            self.mining_total    = hardness

    def tick_mining(self) -> bool:
        if self.mining_target is None or self.mining_total <= 0:
            return False
        self.mining_progress += 1 / self.mining_total
        if self.mining_progress >= 1.0:
            self.mining_target   = None
            self.mining_progress = 0.0
            return True
        return False

    def cancel_mining(self) -> None:
        self.mining_target   = None
        self.mining_progress = 0.0

    # ── Sprite loading & rendering ───────────────────────────────────────────

    def _load_sprites(self) -> None:
        try:
            self._sprite      = self._build_sprite()
            self._sprite_left = pygame.transform.flip(self._sprite, True, False)
        except Exception:
            self._sprite = self._sprite_left = None

    def _build_sprite(self) -> pygame.Surface:
        HEAD_H = 20; BODY_H = 18; LEGS_H = 16; W = 18
        surface = pygame.Surface((W, HEAD_H + BODY_H + LEGS_H), pygame.SRCALPHA)
        skin = (235, 195, 153)

        # Head
        pygame.draw.rect(surface, skin, (1, 0, W - 2, HEAD_H))
        face_path = os.path.join(SKINS_DIR, "male_face_0.png")
        if os.path.exists(face_path):
            face = pygame.image.load(face_path).convert_alpha()
            front = pygame.transform.scale(face.subsurface((0, 0, 16, 16)),
                                           (W - 2, HEAD_H))
            surface.blit(front, (1, 0))
        pygame.draw.rect(surface, (80, 50, 20), (1, 0, W - 2, 4))   # hair

        # Body
        bt = HEAD_H
        pygame.draw.rect(surface, (60, 120, 200), (1, bt, W - 2, BODY_H))
        pygame.draw.rect(surface, skin, (0, bt, 3, BODY_H))
        pygame.draw.rect(surface, skin, (W - 3, bt, 3, BODY_H))

        # Legs
        lt = HEAD_H + BODY_H
        pygame.draw.rect(surface, (40, 40, 100), (1, lt, W // 2 - 2, LEGS_H))
        pygame.draw.rect(surface, (40, 40, 100), (W // 2 + 1, lt, W // 2 - 2, LEGS_H))
        pygame.draw.rect(surface, (80, 50, 20), (1, lt + LEGS_H - 4, W // 2 - 2, 4))
        pygame.draw.rect(surface, (80, 50, 20), (W // 2 + 1, lt + LEGS_H - 4, W // 2 - 2, 4))
        return surface

    def draw(self, surface: pygame.Surface, screen_x: int, screen_y: int,
             block_size: int) -> None:
        sprite = self._sprite_left if self.facing == -1 else self._sprite
        tw = int(block_size * self.WIDTH)
        th = int(block_size * self.HEIGHT)
        if sprite:
            scaled = pygame.transform.scale(sprite, (tw, th))
            ox = screen_x + (block_size - tw) // 2
            surface.blit(scaled, (ox, screen_y))
        else:
            pygame.draw.rect(surface, (200, 150, 80),
                             (screen_x + block_size // 8, screen_y, tw, th))
