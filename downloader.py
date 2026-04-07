"""
First-run asset setup: downloads the original APK from Google Drive and
extracts the game resources if they are not already present.

Called automatically by main.py before the game window opens.
"""
from __future__ import annotations

import os
import sys
import zipfile
import tempfile
import shutil
import urllib.request
import urllib.error
import re
import http.cookiejar

# ── Constants ─────────────────────────────────────────────────────────────────

GAME_DIR    = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR  = os.path.join(GAME_DIR, "apk_extracted", "assets", "GameResources")
APK_FILE_ID = "1VUEukcKamGYcS_84XE4xtp7dTK1CbBWY"

# Primary URL; if Google shows a virus-scan bypass page we parse the real link
_GDRIVE_URL = f"https://drive.usercontent.google.com/download?id={APK_FILE_ID}&export=download&confirm=t"


def assets_present() -> bool:
    """Return True if the game assets are already extracted."""
    marker = os.path.join(ASSETS_DIR, "HDTex", "TileMap.png")
    return os.path.exists(marker)


def run_setup(progress_cb=None) -> None:
    """
    Download and extract the APK assets.
    progress_cb(message: str, pct: float | None) — optional progress callback.
    """
    def _msg(text: str, pct: float | None = None) -> None:
        if progress_cb:
            progress_cb(text, pct)
        else:
            print(text)

    if assets_present():
        return

    _msg("Téléchargement des ressources du jeu (≈ 96 Mo)…", 0.0)

    apk_path = os.path.join(GAME_DIR, "_blockheads_tmp.apk")
    try:
        _download_gdrive(APK_FILE_ID, apk_path, _msg)
        _msg("Extraction des ressources…", 0.9)
        _extract_apk(apk_path, GAME_DIR, _msg)
        _msg("Installation terminée.", 1.0)
    finally:
        if os.path.exists(apk_path):
            os.remove(apk_path)


# ── Download helpers ──────────────────────────────────────────────────────────

def _download_gdrive(file_id: str, dest: str,
                     msg_cb) -> None:
    """Download a Google Drive file, handling the virus-scan confirmation."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar)
    )
    opener.addheaders = [
        ("User-Agent",
         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
         "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"),
    ]

    url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"

    try:
        resp = opener.open(url)
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Impossible de joindre Google Drive : {e}\n"
            "Vérifiez votre connexion Internet."
        ) from e

    # If we landed on an HTML page, find the real download link
    content_type = resp.headers.get("Content-Type", "")
    if "text/html" in content_type:
        html = resp.read().decode("utf-8", errors="ignore")
        # Look for action URL in the confirmation form
        m = re.search(r'action="([^"]+)"', html)
        if not m:
            raise RuntimeError(
                "Impossible de trouver le lien de téléchargement dans la "
                "page Google Drive. Essayez de télécharger l'APK manuellement."
            )
        confirm_url = m.group(1).replace("&amp;", "&")
        # Also gather hidden fields
        fields = re.findall(r'<input[^>]+name="([^"]+)"[^>]+value="([^"]+)"', html)
        params = urllib.parse.urlencode(dict(fields))
        if params:
            confirm_url = confirm_url + ("&" if "?" in confirm_url else "?") + params
        try:
            resp = opener.open(confirm_url)
        except urllib.error.URLError as e:
            raise RuntimeError(f"Erreur confirmation Google Drive : {e}") from e

    _stream_to_file(resp, dest, msg_cb)


def _stream_to_file(resp, dest: str, msg_cb) -> None:
    """Stream an HTTP response body to a file, reporting progress."""
    total = int(resp.headers.get("Content-Length") or 0)
    downloaded = 0
    chunk = 65536

    with open(dest, "wb") as fh:
        while True:
            data = resp.read(chunk)
            if not data:
                break
            fh.write(data)
            downloaded += len(data)
            if total:
                pct = 0.05 + 0.80 * (downloaded / total)
                mb = downloaded / 1_048_576
                total_mb = total / 1_048_576
                msg_cb(
                    f"Téléchargement… {mb:.1f} / {total_mb:.1f} Mo",
                    pct,
                )


def _extract_apk(apk_path: str, dest_dir: str, msg_cb) -> None:
    """Extract the APK (which is a ZIP) into dest_dir/apk_extracted/."""
    out = os.path.join(dest_dir, "apk_extracted")
    os.makedirs(out, exist_ok=True)
    with zipfile.ZipFile(apk_path, "r") as zf:
        members = zf.infolist()
        total   = len(members)
        for i, member in enumerate(members):
            zf.extract(member, out)
            if i % 100 == 0:
                pct = 0.85 + 0.14 * (i / total)
                msg_cb(f"Extraction… {i}/{total} fichiers", pct)


# ── Pygame splash screen (shown while downloading) ────────────────────────────

def run_setup_with_splash() -> None:
    """
    Show a pygame splash/loading screen while the assets download.
    Called from main.py when assets are missing.
    """
    if assets_present():
        return

    import pygame

    pygame.init()
    screen = pygame.display.set_mode((600, 300))
    pygame.display.set_caption("The Blockheads – Installation")

    font_big = pygame.font.SysFont("monospace", 22, bold=True)
    font_sm  = pygame.font.SysFont("monospace", 14)
    clock    = pygame.time.Clock()

    # Icon
    icon_path = os.path.join(GAME_DIR, "apk_extracted", "assets",
                             "GameResources", "114Icon.png")

    state   = {"msg": "Préparation…", "pct": 0.0, "done": False, "error": None}

    def progress(msg: str, pct: float | None) -> None:
        state["msg"] = msg
        if pct is not None:
            state["pct"] = pct
        # Pump pygame events so the window stays responsive
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
        _draw_splash(screen, font_big, font_sm, state)
        pygame.display.flip()
        clock.tick(30)

    # Run download in a thread so the window stays responsive
    import threading
    def worker():
        try:
            run_setup(progress_cb=progress)
            state["done"] = True
            state["pct"]  = 1.0
            state["msg"]  = "Prêt !"
        except Exception as exc:
            state["error"] = str(exc)
            state["msg"]   = f"Erreur : {exc}"

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    while t.is_alive() or not state["done"]:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
        _draw_splash(screen, font_big, font_sm, state)
        pygame.display.flip()
        clock.tick(30)

        if state["error"]:
            # Show error for 5 seconds then exit
            import time
            time.sleep(5)
            pygame.quit()
            sys.exit(1)


def _draw_splash(screen: "pygame.Surface", font_big, font_sm, state: dict) -> None:
    import pygame
    sw, sh = screen.get_size()
    screen.fill((20, 25, 40))

    # Title
    title = font_big.render("The Blockheads  –  PC Edition", True, (255, 220, 80))
    screen.blit(title, (sw // 2 - title.get_width() // 2, 50))

    # Subtitle
    sub = font_sm.render("Téléchargement des ressources du jeu…", True, (180, 180, 200))
    screen.blit(sub, (sw // 2 - sub.get_width() // 2, 95))

    # Progress bar
    bar_w, bar_h = 480, 22
    bx = (sw - bar_w) // 2
    by = 140
    pygame.draw.rect(screen, (50, 55, 70), (bx, by, bar_w, bar_h))
    fill = int(bar_w * min(1.0, max(0.0, state["pct"])))
    if fill > 0:
        pygame.draw.rect(screen, (255, 180, 30), (bx, by, fill, bar_h))
    pygame.draw.rect(screen, (120, 120, 140), (bx, by, bar_w, bar_h), 2)

    # Message
    msg = font_sm.render(state["msg"], True, (220, 220, 220))
    screen.blit(msg, (sw // 2 - msg.get_width() // 2, by + bar_h + 10))

    # Note
    note = font_sm.render(
        "Connexion Internet requise pour la première installation.",
        True, (100, 100, 120),
    )
    screen.blit(note, (sw // 2 - note.get_width() // 2, sh - 40))


# Allow manual run: python downloader.py
if __name__ == "__main__":
    run_setup()
