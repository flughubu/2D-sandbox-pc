"""
Main game class: event loop, camera, block interaction, zoom, pathfinding.
"""
from __future__ import annotations

import math
import os
import sys

import pygame

from tiles import (
    AIR, WATER, LAVA, TORCH_BLOCK,
    SOLID_BLOCKS, LIQUID_BLOCKS,
    BLOCK_HARDNESS, BLOCK_DROP, BLOCK_NAMES,
)
from crafting import PLACEABLE_ITEMS
from world     import World, WORLD_WIDTH, WORLD_HEIGHT
from player    import Player
from renderer  import Renderer
from ui        import HUD
from lighting  import LightingSystem
from pathfinder import find_path

DEFAULT_W  = 1280
DEFAULT_H  = 720
TARGET_FPS = 60
DAY_SECS   = 20 * 60    # 20 real minutes per day
REACH      =  6.0       # max interaction distance in blocks


class Camera:
    SMOOTH = 0.12

    def __init__(self, w: int, h: int, block_size: int):
        self.x = 0.0; self.y = 0.0
        self.w = w;   self.h = h
        self.bs = block_size

    def follow(self, tx: float, ty: float) -> None:
        bx = self.w / self.bs; by = self.h / self.bs
        self.x += ((tx + 0.5 - bx / 2) - self.x) * self.SMOOTH
        self.y += ((ty + 0.5 - by / 2) - self.y) * self.SMOOTH
        self.y  = max(0.0, min(WORLD_HEIGHT - by, self.y))

    def snap(self, tx: float, ty: float) -> None:
        bx = self.w / self.bs; by = self.h / self.bs
        self.x = tx + 0.5 - bx / 2
        self.y = max(0.0, min(WORLD_HEIGHT - by, ty + 0.5 - by / 2))

    def world_to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        return (wx - self.x) * self.bs, (wy - self.y) * self.bs

    def screen_to_world(self, sx: int, sy: int) -> tuple[int, int]:
        bx = int(sx / self.bs + self.x)
        by = int(sy / self.bs + self.y)
        return bx % WORLD_WIDTH, by

    def resize(self, w: int, h: int, bs: int) -> None:
        self.w = w; self.h = h; self.bs = bs

    @property
    def zoom_radius(self) -> int:
        return max(self.w, self.h) // (2 * self.bs) + 4


class Game:
    def __init__(self, screen: pygame.Surface, seed: int | None = None):
        self.screen = screen
        self.sw, self.sh = screen.get_size()

        print("Génération du monde…")
        self.world    = World(seed)
        self.renderer = Renderer(screen)
        self.camera   = Camera(self.sw, self.sh, self.renderer.block_size)
        self.hud      = HUD(screen, self.renderer)
        self.clock    = pygame.time.Clock()

        sx = WORLD_WIDTH // 2
        sy = self.world.surface_y(sx) - 2
        self.player = Player(self.world, float(sx), float(sy))

        self.lighting = LightingSystem(self.world)
        self.camera.snap(self.player.x, self.player.y)

        self.time_of_day  = 0.35
        self.running      = True
        self._paused      = False
        self._font_big    = pygame.font.SysFont("monospace", 40, bold=True)

        # Pending click action (set by mouse click, consumed by pathfinder)
        self._pending_action: dict | None = None

        # Sounds
        self._sounds: dict[str, pygame.mixer.Sound | None] = {}
        self._load_sounds()

    # ── Audio ─────────────────────────────────────────────────────────────────

    def _load_sounds(self) -> None:
        adir = os.path.join(os.path.dirname(__file__),
                            "apk_extracted", "assets", "GameResources")
        for key, fname in [("dig", "dig.wav"), ("place", "place.wav"),
                           ("click", "click.wav")]:
            p = os.path.join(adir, fname)
            if os.path.exists(p):
                try:
                    s = pygame.mixer.Sound(p); s.set_volume(0.4)
                    self._sounds[key] = s
                except Exception:
                    self._sounds[key] = None
            else:
                self._sounds[key] = None

    def _play(self, name: str) -> None:
        s = self._sounds.get(name)
        if s: s.play()

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(TARGET_FPS) / 1000.0, 0.05)
            self._handle_events()
            if not self._paused:
                self._update(dt)
            self._draw()
            pygame.display.flip()

    # ── Events ────────────────────────────────────────────────────────────────

    def _handle_events(self) -> None:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False

            elif ev.type == pygame.KEYDOWN:
                self._on_keydown(ev)

            elif ev.type == pygame.MOUSEBUTTONDOWN:
                self._on_mouse_down(ev)

            elif ev.type == pygame.MOUSEBUTTONUP:
                if self.hud.show_inventory:
                    self.hud.inventory_mouse_up(ev.pos)

            elif ev.type == pygame.MOUSEMOTION:
                if self.hud.show_inventory:
                    self.hud.inventory_mouse_move(ev.pos)

            elif ev.type == pygame.MOUSEWHEEL:
                self.hud.scroll_slot(-ev.y)

            elif ev.type == pygame.VIDEORESIZE:
                self.sw, self.sh = ev.w, ev.h
                self.renderer.resize(ev.w, ev.h)
                self.camera.resize(ev.w, ev.h, self.renderer.block_size)

            # Pathfinding completion events
            elif ev.type == pygame.USEREVENT:
                self._on_user_event(ev)

    def _on_keydown(self, ev: pygame.event.Event) -> None:
        if ev.key == pygame.K_ESCAPE:
            self._paused = not self._paused
        elif ev.key == pygame.K_e:
            self.hud.show_inventory = not self.hud.show_inventory
        elif ev.key == pygame.K_F11:
            pygame.display.toggle_fullscreen()
        # Zoom: + / =  and  -
        elif ev.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self.renderer.zoom(+1)
            self.camera.resize(self.sw, self.sh, self.renderer.block_size)
        elif ev.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.renderer.zoom(-1)
            self.camera.resize(self.sw, self.sh, self.renderer.block_size)
        # Number keys
        for i, k in enumerate([pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4,
                                pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8,
                                pygame.K_9]):
            if ev.key == k:
                self.hud.select_slot(i)

    def _on_mouse_down(self, ev: pygame.event.Event) -> None:
        # Inventory absorbs clicks
        if self.hud.show_inventory:
            self.hud.inventory_mouse_down(ev.pos)
            return

        if ev.button == 1:   # left click → mine
            bx, by = self.camera.screen_to_world(*ev.pos)
            block  = self.world.get(bx, by)
            if block != AIR and block not in LIQUID_BLOCKS:
                self._request_path_action("mine", bx, by)

        elif ev.button == 3:  # right click → place
            bx, by = self.camera.screen_to_world(*ev.pos)
            if self.hud.selected_block != AIR:
                self._request_path_action("place", bx, by,
                                          self.hud.selected_block)

        elif ev.button in (4, 5):
            self.hud.scroll_slot(1 if ev.button == 5 else -1)

    def _on_user_event(self, ev: pygame.event.Event) -> None:
        sub = getattr(ev, "subtype", None)
        if sub == "mine_reached":
            bx, by = ev.pos
            self._do_mine(bx, by)
        elif sub == "place_reached":
            bx, by = ev.pos
            self._do_place(bx, by, ev.block)

    # ── Pathfinding requests ──────────────────────────────────────────────────

    def _request_path_action(self, action: str, bx: int, by: int,
                             place_block: int = AIR) -> None:
        p  = self.player
        sx = int(p.x + p.WIDTH / 2)
        sy = int(p.y + p.HEIGHT - 0.01)
        path = find_path(self.world, sx, sy, bx, by)

        if not path:
            # Already adjacent or unreachable → act immediately if close enough
            dist = math.hypot(bx + 0.5 - (p.x + p.WIDTH/2),
                              by + 0.5 - (p.y + p.HEIGHT/2))
            if dist <= REACH:
                if action == "mine":
                    self._do_mine(bx, by)
                elif action == "place":
                    self._do_place(bx, by, place_block)
            return

        p.set_path(path, action, (bx, by), place_block)

    # ── Block actions ─────────────────────────────────────────────────────────

    def _do_mine(self, bx: int, by: int) -> None:
        block = self.world.get(bx, by)
        if block == AIR or block in LIQUID_BLOCKS:
            return
        hardness = BLOCK_HARDNESS.get(block, 60)
        if hardness == 0:
            return
        # Start mining progress (ticked next frames)
        self.player.start_mining(bx, by, hardness)
        self._mining_auto = True   # flag so update() keeps ticking

    def _finish_mine(self, bx: int, by: int) -> None:
        block = self.world.get(bx, by)
        drop  = BLOCK_DROP.get(block, block)
        self.world.set(bx, by, AIR)
        self.hud.add_item(drop)
        self._play("dig")

    def _do_place(self, bx: int, by: int, block: int) -> None:
        # Non-placeable crafted items (e.g. tools, ingots)
        if block >= 100 and block not in PLACEABLE_ITEMS:
            return
        existing = self.world.get(bx, by)
        if existing not in (AIR, WATER, LAVA):
            return
        # Don't place inside player
        p = self.player
        if (int(p.x) <= bx <= int(p.x + p.WIDTH) and
                int(p.y) <= by <= int(p.y + p.HEIGHT)):
            return
        self.world.set(bx, by, block)
        self._play("place")

    # ── Update ────────────────────────────────────────────────────────────────

    def __init_mining_auto(self):
        if not hasattr(self, "_mining_auto"):
            self._mining_auto = False

    def _update(self, dt: float) -> None:
        self.__init_mining_auto()
        self.time_of_day = (self.time_of_day + dt / DAY_SECS) % 1.0

        keys = pygame.key.get_pressed()
        self.player.update(keys, dt)
        self.camera.follow(self.player.x, self.player.y)

        # Tick mining progress
        if self._mining_auto and self.player.mining_target:
            target = self.player.mining_target   # save before tick resets it
            done   = self.player.tick_mining()
            if done:
                self._mining_auto = False
                self._finish_mine(*target)
        elif self._mining_auto:
            self._mining_auto = False

        # Update lighting (throttled: every other frame)
        if int(self.time_of_day * TARGET_FPS * DAY_SECS) % 2 == 0:
            px = int(self.player.x + self.player.WIDTH / 2)
            py = int(self.player.y + self.player.HEIGHT / 2)
            self.lighting.update(px, py, self.time_of_day,
                                 self.camera.zoom_radius)

    # ── Draw ──────────────────────────────────────────────────────────────────

    def _draw(self) -> None:
        self.renderer.draw_world(
            self.world, self.camera.x, self.camera.y,
            self.time_of_day, self.lighting,
        )

        sx, sy = self.camera.world_to_screen(self.player.x, self.player.y)
        self.player.draw(self.screen, int(sx), int(sy), self.renderer.block_size)

        # Block highlight
        hovered = None
        if not self.hud.show_inventory and not self._paused:
            mx, my = pygame.mouse.get_pos()
            hbx, hby = self.camera.screen_to_world(mx, my)
            b = self.world.get(hbx, hby)
            if b != AIR:
                hovered = b
                hsx = int((hbx - self.camera.x) * self.renderer.block_size)
                hsy = int((hby - self.camera.y) * self.renderer.block_size)
                BS  = self.renderer.block_size
                hl  = pygame.Surface((BS, BS), pygame.SRCALPHA)
                hl.fill((255, 255, 255, 50))
                pygame.draw.rect(hl, (255, 255, 255, 150), hl.get_rect(), 2)
                self.screen.blit(hl, (hsx, hsy))

        self.hud.draw(self.player, self.time_of_day, hovered)
        if self.hud.show_inventory:
            self.hud.draw_inventory_overlay()
        if self._paused:
            self._draw_pause()

    def _draw_pause(self) -> None:
        ov = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 120))
        self.screen.blit(ov, (0, 0))
        lbl  = self._font_big.render("PAUSE", True, (255, 255, 255))
        hint = pygame.font.SysFont("monospace", 20).render(
            "Appuyez sur Échap pour reprendre", True, (200, 200, 200))
        self.screen.blit(lbl,  (self.sw//2 - lbl.get_width()//2,  self.sh//2 - 30))
        self.screen.blit(hint, (self.sw//2 - hint.get_width()//2, self.sh//2 + 20))
