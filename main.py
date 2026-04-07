#!/usr/bin/env python3
"""
The Blockheads – PC Edition
Entry point. Run with:  python main.py  (or  ./run.sh)
"""
import sys
import os

# Make sure we can import project modules regardless of cwd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame

from downloader import assets_present, run_setup_with_splash
from game import Game, DEFAULT_W, DEFAULT_H


def main() -> None:
    pygame.init()
    pygame.mixer.pre_init(44100, -16, 2, 512)
    pygame.mixer.init()

    # First-run: download game assets if missing
    if not assets_present():
        run_setup_with_splash()

    # Window
    flags  = pygame.RESIZABLE
    screen = pygame.display.set_mode((DEFAULT_W, DEFAULT_H), flags)
    pygame.display.set_caption("The Blockheads – PC Edition")

    # App icon
    icon_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "apk_extracted", "assets", "GameResources", "114Icon.png",
    )
    if os.path.exists(icon_path):
        try:
            pygame.display.set_icon(pygame.image.load(icon_path))
        except Exception:
            pass

    # Parse optional --seed argument
    seed = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg.startswith("--seed="):
            try:
                seed = int(arg.split("=", 1)[1])
            except ValueError:
                pass
        elif arg == "--seed" and i < len(sys.argv) - 1:
            try:
                seed = int(sys.argv[i + 1])
            except ValueError:
                pass

    game = Game(screen, seed=seed)
    game.run()

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
