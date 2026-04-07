"""
Main game class: event loop, camera, block interaction, audio.
"""
from __future__ import annotations

import math
import os
import random
import sys

import pygame

from tiles import (
    AIR, WATER, LAVA, SOLID_BLOCKS, LIQUID_BLOCKS,
    BLOCK_HARDNESS, BLOCK_DROP, BLOCK_NAMES,
    HOTBAR_DEFAULTS,
)
from world  import World, WORLD_WIDTH, WORLD_HEIGHT
from player import Player, BLOCK_SIZE
from renderer import Renderer
from ui      import HUD

# ── Screen defaults ────────────────────────────────────────────────────────────
DEFAULT_W  = 1280
DEFAULT_H  = 720
TARGET_FPS = 60

# ── Day / night cycle ──────────────────────────────────────────────────────────
DAY_DURATION_SECS = 20 * 60   # 20 real minutes = one full day

ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "apk_extracted", "assets", "GameResources",
)

# Reach distance in blocks
REACH = 5.0


class Camera:
    """Smooth-following camera (position in block coordinates)."""

    SMOOTH = 0.12   # lerp factor per frame

    def __init__(self, w: int, h: int):
        self.x    = 0.0   # world-space top-left column
        self.y    = 0.0   # world-space top-left row
        self.w    = w     # screen width in pixels
        self.h    = h     # screen height in pixels

    def follow(self, target_bx: float, target_by: float) -> None:
        """Lerp towards player position."""
        blocks_x = self.w / BLOCK_SIZE
        blocks_y = self.h / BLOCK_SIZE
        target_cx = target_bx + 0.5 - blocks_x / 2
        target_cy = target_by + 0.5 - blocks_y / 2
        self.x += (target_cx - self.x) * self.SMOOTH
        self.y += (target_cy - self.y) * self.SMOOTH
        # Clamp vertically
        self.y = max(0.0, min(WORLD_HEIGHT - blocks_y, self.y))

    def resize(self, w: int, h: int) -> None:
        self.w, self.h = w, h

    def world_to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        return (wx - self.x) * BLOCK_SIZE, (wy - self.y) * BLOCK_SIZE

    def screen_to_world(self, sx: int, sy: int) -> tuple[int, int]:
        bx = int(sx / BLOCK_SIZE + self.x)
        by = int(sy / BLOCK_SIZE + self.y)
        return bx % WORLD_WIDTH, by


class Game:
    """Top-level game object; owns the main loop."""

    def __init__(self, screen: pygame.Surface, seed: int | None = None):
        self.screen = screen
        self.sw, self.sh = screen.get_size()

        # ── Sub-systems ────────────────────────────────────────────────────
        print("Generating world…")
        self.world    = World(seed)
        self.renderer = Renderer(screen)
        self.camera   = Camera(self.sw, self.sh)
        self.hud      = HUD(screen, self.renderer)
        self.clock    = pygame.time.Clock()

        # Spawn player near the centre of the world
        spawn_x = WORLD_WIDTH // 2
        spawn_y = self.world.surface_y(spawn_x) - 2
        self.player = Player(self.world, float(spawn_x), float(spawn_y))

        # Centre camera immediately (no lerp)
        for _ in range(60):
            self.camera.follow(self.player.x, self.player.y)

        # ── State ──────────────────────────────────────────────────────────
        self.time_of_day   = 0.35   # start just after dawn (~0.35 ≈ early morning)
        self.running       = True
        self.show_inventory = False

        # Inventory for creative mode (all block types player can place)
        from tiles import HOTBAR_DEFAULTS
        from tiles import (STONE, DIRT, GRASS, SAND, GRAVEL, WOOD, LEAVES,
                           COAL_ORE, IRON_ORE, GOLD_ORE, LIMESTONE, MARBLE,
                           SNOW, ICE, LADDER, FLINT, WATER, LAVA)
        self.inventory = [
            STONE, DIRT, GRASS, SAND, GRAVEL, WOOD, LEAVES,
            COAL_ORE, IRON_ORE, GOLD_ORE, LIMESTONE, MARBLE,
            SNOW, ICE, LADDER, FLINT, WATER, LAVA,
        ]

        # Mining / placing state
        self._lmb_held       = False
        self._rmb_held       = False
        self._rmb_last_place: tuple[int, int] | None = None  # avoid spam

        # Sounds
        self._sounds: dict[str, pygame.mixer.Sound | None] = {}
        self._load_sounds()

        # Paused message
        self._paused = False
        self._font_big = pygame.font.SysFont("monospace", 40, bold=True)

    # ── Audio ─────────────────────────────────────────────────────────────────

    def _load_sounds(self) -> None:
        want = {
            "dig":   "dig.wav",
            "place": "place.wav",
            "click": "click.wav",
        }
        for key, fname in want.items():
            path = os.path.join(ASSETS_DIR, fname)
            if os.path.exists(path):
                try:
                    self._sounds[key] = pygame.mixer.Sound(path)
                    self._sounds[key].set_volume(0.4)
                except Exception:
                    self._sounds[key] = None
            else:
                self._sounds[key] = None

    def _play(self, name: str) -> None:
        snd = self._sounds.get(name)
        if snd:
            snd.play()

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            dt = min(dt, 0.05)   # cap to avoid spiral-of-death on lag

            self._handle_events()
            if not self._paused:
                self._update(dt)
            self._draw()
            pygame.display.flip()

    # ── Events ────────────────────────────────────────────────────────────────

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.KEYDOWN:
                self._on_keydown(event)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._on_mouse_down(event)

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    self._lmb_held = False
                    self.player.cancel_mining()
                if event.button == 3:
                    self._rmb_held       = False
                    self._rmb_last_place = None

            elif event.type == pygame.MOUSEWHEEL:
                self.hud.scroll_slot(-event.y)

            elif event.type == pygame.VIDEORESIZE:
                self.sw, self.sh = event.w, event.h
                self.renderer.resize(event.w, event.h)
                self.camera.resize(event.w, event.h)

    def _on_keydown(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_ESCAPE:
            self._paused = not self._paused
        elif event.key == pygame.K_e:
            self.show_inventory = not self.show_inventory
        elif event.key in (pygame.K_F11,):
            pygame.display.toggle_fullscreen()
        # Number keys 1-9 select hotbar slot
        for i, key in enumerate([
            pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5,
            pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9,
        ]):
            if event.key == key:
                self.hud.select_slot(i)

    def _on_mouse_down(self, event: pygame.event.Event) -> None:
        if self.show_inventory:
            if event.button == 1:
                idx = self.hud.inventory_slot_at(event.pos, self.inventory)
                if idx is not None:
                    # Put clicked block into selected hotbar slot
                    self.hud.hotbar[self.hud.sel_slot] = self.inventory[idx]
            return

        if event.button == 1:
            self._lmb_held = True
        elif event.button == 3:
            self._rmb_held = True
            self._try_place(event.pos)
        elif event.button in (4, 5):   # legacy scroll
            self.hud.scroll_slot(1 if event.button == 5 else -1)

    # ── Update ────────────────────────────────────────────────────────────────

    def _update(self, dt: float) -> None:
        # Day/night cycle
        self.time_of_day = (self.time_of_day + dt / DAY_DURATION_SECS) % 1.0

        # Player movement
        keys = pygame.key.get_pressed()
        self.player.update(keys, dt)

        # Camera
        self.camera.follow(self.player.x, self.player.y)

        # Mining (held left mouse)
        if self._lmb_held and not self.show_inventory:
            self._tick_mining()

        # Continuous placement (held right mouse – only in new block)
        if self._rmb_held and not self.show_inventory:
            mx, my = pygame.mouse.get_pos()
            self._try_place((mx, my))

    # ── Mining ────────────────────────────────────────────────────────────────

    def _tick_mining(self) -> None:
        mx, my = pygame.mouse.get_pos()
        bx, by = self.camera.screen_to_world(mx, my)
        block  = self.world.get(bx, by)

        if block == AIR or block in LIQUID_BLOCKS:
            self.player.cancel_mining()
            return

        # Range check
        px = self.player.x + self.player.WIDTH / 2
        py = self.player.y + self.player.HEIGHT / 2
        dist = math.hypot(bx + 0.5 - px, by + 0.5 - py)
        if dist > REACH:
            self.player.cancel_mining()
            return

        hardness = BLOCK_HARDNESS.get(block, 60)
        if hardness == 0:
            self.player.cancel_mining()
            return

        self.player.start_mining(bx, by, hardness)
        broken = self.player.tick_mining()

        if broken:
            drop = BLOCK_DROP.get(block, block)
            self.world.set(bx, by, AIR)
            self._play("dig")
            # Add drop to inventory / hotbar (first empty or matching slot)
            self._auto_collect(drop)

    def _auto_collect(self, block: int) -> None:
        """Try to put a block into an existing hotbar stack or an empty slot."""
        for i, b in enumerate(self.hud.hotbar):
            if b == block:
                return   # already have it
        for i, b in enumerate(self.hud.hotbar):
            if b == AIR:
                self.hud.hotbar[i] = block
                return

    # ── Placement ─────────────────────────────────────────────────────────────

    def _try_place(self, mouse_pos: tuple[int, int]) -> None:
        block_to_place = self.hud.selected_block
        if block_to_place == AIR:
            return

        bx, by = self.camera.screen_to_world(*mouse_pos)

        # Don't place on same spot twice in one hold
        if (bx, by) == self._rmb_last_place:
            return

        existing = self.world.get(bx, by)
        if existing not in (AIR, WATER, LAVA):
            return   # spot already occupied

        # Range check
        px = self.player.x + self.player.WIDTH / 2
        py = self.player.y + self.player.HEIGHT / 2
        dist = math.hypot(bx + 0.5 - px, by + 0.5 - py)
        if dist > REACH:
            return

        # Don't place inside player
        pb_left  = int(self.player.x)
        pb_right = int(self.player.x + self.player.WIDTH)
        pb_top   = int(self.player.y)
        pb_bot   = int(self.player.y + self.player.HEIGHT)
        if pb_left <= bx <= pb_right and pb_top <= by <= pb_bot:
            return

        self.world.set(bx, by, block_to_place)
        self._rmb_last_place = (bx, by)
        self._play("place")

    # ── Draw ──────────────────────────────────────────────────────────────────

    def _draw(self) -> None:
        # World
        self.renderer.draw_world(
            self.world, self.camera.x, self.camera.y, self.time_of_day
        )

        # Player
        sx, sy = self.camera.world_to_screen(self.player.x, self.player.y)
        self.player.draw(self.screen, int(sx), int(sy), BLOCK_SIZE)

        # Block highlight under cursor
        hovered = None
        if not self.show_inventory and not self._paused:
            mx, my = pygame.mouse.get_pos()
            hbx, hby = self.camera.screen_to_world(mx, my)
            hovered = self.world.get(hbx, hby)
            if hovered != AIR:
                hsx = int((hbx - self.camera.x) * BLOCK_SIZE)
                hsy = int((hby - self.camera.y) * BLOCK_SIZE)
                hl  = pygame.Surface((BLOCK_SIZE, BLOCK_SIZE), pygame.SRCALPHA)
                hl.fill((255, 255, 255, 50))
                pygame.draw.rect(hl, (255, 255, 255, 150), hl.get_rect(), 2)
                self.screen.blit(hl, (hsx, hsy))
            else:
                hovered = None

        # HUD
        self.hud.draw(self.player, self.time_of_day, hovered)

        # Inventory overlay
        if self.show_inventory:
            self.hud.draw_inventory(self.inventory)

        # Paused screen
        if self._paused:
            self._draw_pause()

    def _draw_pause(self) -> None:
        overlay = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        self.screen.blit(overlay, (0, 0))
        label = self._font_big.render("PAUSED", True, (255, 255, 255))
        hint  = pygame.font.SysFont("monospace", 20).render(
            "Press Esc to resume", True, (200, 200, 200))
        self.screen.blit(label, (self.sw // 2 - label.get_width() // 2,
                                 self.sh // 2 - 30))
        self.screen.blit(hint,  (self.sw // 2 - hint.get_width() // 2,
                                 self.sh // 2 + 20))
