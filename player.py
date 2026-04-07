"""
Player entity: physics, controls, character rendering.
"""
from __future__ import annotations

import os
import math
from typing import TYPE_CHECKING

import pygame

from tiles import SOLID_BLOCKS, LIQUID_BLOCKS, LADDER

if TYPE_CHECKING:
    from world import World

# ── Physics constants ────────────────────────────────────────────────────────
GRAVITY       =  0.45   # blocks / frame²
JUMP_FORCE    = -9.0    # blocks / frame  (negative = upward)
MAX_FALL      =  14.0   # blocks / frame
WALK_SPEED    =  4.5    # blocks / second
RUN_SPEED     =  7.0    # blocks / second
LIQUID_SPEED  =  2.5    # blocks / second (in water)
LIQUID_JUMP   = -5.0
FRICTION      =  0.82   # horizontal damping on ground
AIR_FRICTION  =  0.92
FPS           =  60

BLOCK_SIZE    = 32      # pixel size of one block on screen (set by renderer)

ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "apk_extracted", "assets", "GameResources",
)
SKINS_DIR = os.path.join(ASSETS_DIR, "skins")
HD_DIR    = os.path.join(ASSETS_DIR, "HDTex")


class Player:
    """2-D physics entity representing the player's blockhead."""

    # Collision box in blocks
    WIDTH  = 0.75
    HEIGHT = 1.80

    def __init__(self, world: "World", x: float, y: float):
        self.world = world

        # Position in block coordinates (top-left of bounding box)
        self.x = x
        self.y = y

        # Velocity in blocks / frame
        self.vx = 0.0
        self.vy = 0.0

        self.on_ground = False
        self.in_liquid = False
        self.facing    = 1   # 1 = right, -1 = left

        # Mining state
        self.mining_target: tuple[int, int] | None = None
        self.mining_progress = 0.0   # 0.0 – 1.0
        self.mining_total    = 0

        # Sprite surfaces (loaded lazily)
        self._sprite: pygame.Surface | None = None
        self._sprite_left: pygame.Surface | None = None
        self._load_sprites()

    # ── Input & update ───────────────────────────────────────────────────────

    def update(self, keys: pygame.key.ScancodeWrapper, dt: float) -> None:
        """Called once per frame. dt in seconds (typically 1/60)."""
        frames = dt * FPS   # normalise to 60fps frame units

        in_liquid = self.world.is_liquid(
            int(self.x + self.WIDTH / 2),
            int(self.y + self.HEIGHT * 0.6),
        )
        self.in_liquid = in_liquid

        # ── Horizontal movement ──────────────────────────────────────────
        move_x = 0.0
        speed = LIQUID_SPEED if in_liquid else WALK_SPEED

        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            move_x -= speed / FPS
            self.facing = -1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            move_x += speed / FPS
            self.facing = 1

        self.vx = move_x if move_x != 0 else (
            self.vx * (FRICTION if self.on_ground else AIR_FRICTION)
        )

        # ── Vertical (jump / gravity) ─────────────────────────────────────
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

        # ── Move & collide ────────────────────────────────────────────────
        self._move(self.vx, self.vy * frames)

    def _move(self, dx: float, dy: float) -> None:
        W = self.world.width

        # Horizontal first
        nx = self.x + dx
        if not self._collides(nx, self.y):
            self.x = nx % W
        else:
            # Try a half-step (step-up logic)
            if not self._collides(nx, self.y - 1.0):
                self.x = nx % W
                self.y -= 1.0
            self.vx = 0.0

        # Vertical
        ny = self.y + dy
        if not self._collides(self.x, ny):
            self.y = ny
            self.on_ground = False
        else:
            if dy > 0:  # falling
                self.on_ground = True
            self.vy = 0.0

    def _collides(self, px: float, py: float) -> bool:
        """AABB vs world blocks."""
        world = self.world
        W = world.width
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
        """Advance mining by one frame. Returns True when block is broken."""
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

    # ── Rendering ────────────────────────────────────────────────────────────

    def _load_sprites(self) -> None:
        """Build a composite character sprite from the original game assets."""
        try:
            self._sprite = self._build_sprite()
            self._sprite_left = pygame.transform.flip(self._sprite, True, False)
        except Exception:
            self._sprite = None
            self._sprite_left = None

    def _build_sprite(self) -> pygame.Surface:
        """Compose head + body + legs from the game's skin textures."""
        # Target character height: ~56px for a 32px block (≈1.75 blocks)
        HEAD_H = 20
        BODY_H = 18
        LEGS_H = 16
        WIDTH  = 18

        surface = pygame.Surface((WIDTH, HEAD_H + BODY_H + LEGS_H), pygame.SRCALPHA)
        surface.fill((0, 0, 0, 0))

        skin_color = (235, 195, 153)   # default light skin

        # ── Head ──────────────────────────────────────────────────────────
        head_rect = pygame.Rect(1, 0, WIDTH - 2, HEAD_H)
        pygame.draw.rect(surface, skin_color, head_rect)

        # Overlay face texture
        face_path = os.path.join(SKINS_DIR, "male_face_0.png")
        if os.path.exists(face_path):
            face_img = pygame.image.load(face_path).convert_alpha()
            # face_img is 32×16; left half (16×16) = front face
            front = face_img.subsurface((0, 0, 16, 16))
            front = pygame.transform.scale(front, (WIDTH - 2, HEAD_H))
            surface.blit(front, (1, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(front, (1, 0))

        # Hair
        hair_path = os.path.join(SKINS_DIR, "male_hair_0.png")
        if os.path.exists(hair_path):
            hair_img = pygame.image.load(hair_path).convert_alpha()
            hair_col = (80, 50, 20)
            # Draw a simple hair band at the top
            pygame.draw.rect(surface, hair_col, (1, 0, WIDTH - 2, 4))

        # ── Body ──────────────────────────────────────────────────────────
        body_top = HEAD_H
        shirt_color = (60, 120, 200)   # blue singlet default
        pygame.draw.rect(surface, shirt_color, (1, body_top, WIDTH - 2, BODY_H))
        # Simple shirt detail lines
        pygame.draw.line(surface, (40, 90, 160),
                         (1, body_top + 4), (WIDTH - 2, body_top + 4))

        # Arms (slightly narrower, same height)
        arm_color = skin_color
        pygame.draw.rect(surface, arm_color, (0, body_top, 3, BODY_H))
        pygame.draw.rect(surface, arm_color, (WIDTH - 3, body_top, 3, BODY_H))

        # ── Legs ──────────────────────────────────────────────────────────
        legs_top = HEAD_H + BODY_H
        leg_color = (40, 40, 100)   # dark trousers
        # Left leg
        pygame.draw.rect(surface, leg_color, (1, legs_top, WIDTH // 2 - 2, LEGS_H))
        # Right leg
        pygame.draw.rect(surface, leg_color,
                         (WIDTH // 2 + 1, legs_top, WIDTH // 2 - 2, LEGS_H))
        # Gap between legs
        pygame.draw.line(surface, (0, 0, 0, 0),
                         (WIDTH // 2, legs_top), (WIDTH // 2, legs_top + LEGS_H))

        # Boots
        boot_color = (80, 50, 20)
        pygame.draw.rect(surface, boot_color,
                         (1, legs_top + LEGS_H - 4, WIDTH // 2 - 2, 4))
        pygame.draw.rect(surface, boot_color,
                         (WIDTH // 2 + 1, legs_top + LEGS_H - 4, WIDTH // 2 - 2, 4))

        return surface

    def draw(self, surface: pygame.Surface, screen_x: int, screen_y: int,
             block_size: int) -> None:
        """Render the character centered at its block position."""
        sprite = self._sprite_left if self.facing == -1 else self._sprite
        if sprite is None:
            # Fallback: simple colored rectangle
            r = pygame.Rect(
                screen_x + block_size // 8,
                screen_y,
                int(block_size * self.WIDTH),
                int(block_size * self.HEIGHT),
            )
            pygame.draw.rect(surface, (200, 150, 80), r)
            return

        # Scale sprite to block size
        target_w = int(block_size * self.WIDTH)
        target_h = int(block_size * self.HEIGHT)
        scaled = pygame.transform.scale(sprite, (target_w, target_h))

        ox = screen_x + (block_size - target_w) // 2
        surface.blit(scaled, (ox, screen_y))
