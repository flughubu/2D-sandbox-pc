"""
Simple platformer pathfinding: BFS on reachable positions.

The graph nodes are (block_x, block_y) cells where the player can stand
(feet position). Edges represent: walk left/right, jump up 1, fall down.
"""
from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world import World

# Maximum path length to search (avoids infinite loops)
MAX_SEARCH = 4000
# Maximum horizontal distance before giving up
MAX_DIST   = 120


def _can_stand(world: "World", bx: int, by: int) -> bool:
    """True if player can stand with feet at (bx, by): cell is air, cell below is solid."""
    W = world.width
    bx = bx % W
    return (
        not world.is_solid(bx, by)
        and not world.is_solid(bx, by - 1)          # head clearance
        and (world.is_solid(bx, by + 1) or world.is_liquid(bx, by))
    )


def _neighbors(world: "World", bx: int, by: int):
    """Yield reachable (nx, ny) positions from standing position (bx, by)."""
    W = world.width

    for dx in (-1, 1):
        nx = (bx + dx) % W

        # Walk flat
        if _can_stand(world, nx, by):
            yield nx, by

        # Step up 1 block
        if not world.is_solid(nx, by - 2) and _can_stand(world, nx, by - 1):
            yield nx, by - 1

        # Fall into pit next to us
        for drop in range(1, 5):
            ny = by + drop
            if world.is_solid(nx, ny):
                break
            if _can_stand(world, nx, ny):
                yield nx, ny
                break

    # Fall straight down
    for drop in range(1, 5):
        ny = by + drop
        if world.is_solid(bx, ny):
            break
        if _can_stand(world, bx, ny):
            yield bx, ny
            break


def find_path(world: "World",
              start_bx: int, start_by: int,
              goal_bx: int,  goal_by: int) -> list[tuple[int, int]]:
    """
    BFS from (start_bx, start_by) to any stand-position adjacent to goal block.

    start/goal are *block* coordinates (integer grid positions).
    Returns list of (bx, by) waypoints the player should walk through,
    or [] if no path found.
    """
    W = world.width

    # Snap start to nearest standable cell
    sx, sy = start_bx % W, start_by
    # Allow a small vertical scan in case player is mid-air
    for dy in range(-1, 3):
        if _can_stand(world, sx, sy + dy):
            sy = sy + dy
            break

    # Target: adjacent cells next to the goal block from which the player
    # can reach (mine / place).  We accept any of them.
    targets: set[tuple[int, int]] = set()
    for dx, dy in ((-1, 0), (1, 0), (0, 1), (0, -1)):
        tx, ty = (goal_bx + dx) % W, goal_by + dy
        if _can_stand(world, tx, ty):
            targets.add((tx, ty))

    if not targets:
        return []

    if (sx, sy) in targets:
        return [(sx, sy)]

    # BFS
    queue: deque[tuple[int, int, list]] = deque()
    queue.append((sx, sy, []))
    visited: set[tuple[int, int]] = {(sx, sy)}
    steps = 0

    while queue and steps < MAX_SEARCH:
        cx, cy, path = queue.popleft()
        steps += 1

        for nx, ny in _neighbors(world, cx, cy):
            key = (nx % W, ny)
            if key in visited:
                continue
            # Prune: don't wander too far horizontally
            hdist = min(abs(nx - goal_bx), W - abs(nx - goal_bx))
            if hdist > MAX_DIST:
                continue

            new_path = path + [(cx, cy)]
            if key in targets:
                return new_path + [key]

            visited.add(key)
            queue.append((nx, ny, new_path))

    return []   # No path found within budget
