"""
Crafting system: recipes, crafting grid, result computation.

Recipes are defined as shaped (2×2 or 3×3 pattern) or shapeless.
Items that are not placeable blocks are given IDs >= 100.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from tiles import (
    AIR, STONE, DIRT, GRASS, SAND, GRAVEL, WOOD, LEAVES,
    COAL_ORE, IRON_ORE, GOLD_ORE, LIMESTONE, MARBLE,
    SNOW, ICE, LADDER, FLINT, TORCH_BLOCK, GLASS, CLAY, BASALT,
)

# ── Non-placeable item IDs (>= 100) ──────────────────────────────────────────
STICK        = 100
WOOD_PLANK   = 101
FLINT_KNIFE  = 102
FLINT_SPADE  = 103
FLINT_PICK   = 104
COAL         = 105   # drop from COAL_ORE
IRON_INGOT   = 106   # smelted from IRON_ORE
GOLD_INGOT   = 107   # smelted from GOLD_ORE
CAMPFIRE     = 108
WORKBENCH    = 109   # placeable in-world, but crafted as item first
IRON_PICK    = 110
IRON_SWORD   = 111
IRON_SPADE   = 112
GOLD_PICK    = 113
BREAD        = 114
STRING       = 115

# Item names (merged with BLOCK_NAMES in display)
ITEM_NAMES: dict[int, str] = {
    STICK:       "Bâton",
    WOOD_PLANK:  "Planche",
    FLINT_KNIFE: "Couteau de silex",
    FLINT_SPADE: "Pelle de silex",
    FLINT_PICK:  "Pioche de silex",
    COAL:        "Charbon",
    IRON_INGOT:  "Lingot de fer",
    GOLD_INGOT:  "Lingot d'or",
    CAMPFIRE:    "Feu de camp",
    WORKBENCH:   "Établi",
    IRON_PICK:   "Pioche de fer",
    IRON_SWORD:  "Épée de fer",
    IRON_SPADE:  "Pelle de fer",
    GOLD_PICK:   "Pioche d'or",
    BREAD:       "Pain",
    STRING:      "Ficelle",
}

# Items that can be placed as blocks when selected in hotbar
PLACEABLE_ITEMS: dict[int, int] = {
    WORKBENCH: WORKBENCH,
    CAMPFIRE:  CAMPFIRE,
}

# Tool tier & speed multiplier (vs default 1.0)
TOOL_SPEED: dict[int, float] = {
    FLINT_SPADE: 2.0,
    FLINT_PICK:  2.0,
    FLINT_KNIFE: 1.5,
    IRON_PICK:   4.0,
    IRON_SPADE:  4.0,
    IRON_SWORD:  1.8,
    GOLD_PICK:   6.0,
}


# ── Recipe data ──────────────────────────────────────────────────────────────

@dataclass
class Recipe:
    result:  int          # output item/block ID
    count:   int = 1      # how many produced
    # For shaped recipes: list of rows, each row a list of item IDs (0=AIR)
    pattern: list[list[int]] = field(default_factory=list)
    # For shapeless recipes: unordered list of ingredients
    ingredients: list[int] = field(default_factory=list)

    @property
    def is_shapeless(self) -> bool:
        return bool(self.ingredients) and not self.pattern


# ── Recipe registry ───────────────────────────────────────────────────────────

RECIPES: list[Recipe] = [

    # ── Wood / building ──────────────────────────────────────────────────────
    Recipe(result=WOOD_PLANK, count=4,
           pattern=[[WOOD]]),

    Recipe(result=STICK, count=4,
           pattern=[[WOOD_PLANK],
                    [WOOD_PLANK]]),

    Recipe(result=LADDER, count=3,
           pattern=[[STICK, AIR,   STICK],
                    [STICK, STICK, STICK],
                    [STICK, AIR,   STICK]]),

    Recipe(result=WORKBENCH, count=1,
           pattern=[[WOOD_PLANK, WOOD_PLANK],
                    [WOOD_PLANK, WOOD_PLANK]]),

    # ── Torches ──────────────────────────────────────────────────────────────
    Recipe(result=TORCH_BLOCK, count=4,
           pattern=[[COAL],
                    [STICK]]),

    # ── Fire ─────────────────────────────────────────────────────────────────
    Recipe(result=CAMPFIRE, count=1,
           pattern=[[STICK, WOOD, STICK],
                    [STICK, COAL, STICK]]),

    # ── Flint tools ──────────────────────────────────────────────────────────
    Recipe(result=FLINT_KNIFE, count=1,
           pattern=[[FLINT],
                    [STICK]]),

    Recipe(result=FLINT_SPADE, count=1,
           pattern=[[FLINT],
                    [FLINT],
                    [STICK]]),

    Recipe(result=FLINT_PICK, count=1,
           pattern=[[FLINT, FLINT, FLINT],
                    [AIR,   STICK, AIR  ],
                    [AIR,   STICK, AIR  ]]),

    # ── Iron tools ───────────────────────────────────────────────────────────
    Recipe(result=IRON_PICK, count=1,
           pattern=[[IRON_INGOT, IRON_INGOT, IRON_INGOT],
                    [AIR,        STICK,       AIR       ],
                    [AIR,        STICK,       AIR       ]]),

    Recipe(result=IRON_SPADE, count=1,
           pattern=[[IRON_INGOT],
                    [STICK     ],
                    [STICK     ]]),

    Recipe(result=IRON_SWORD, count=1,
           pattern=[[IRON_INGOT],
                    [IRON_INGOT],
                    [STICK     ]]),

    # ── Gold tools ───────────────────────────────────────────────────────────
    Recipe(result=GOLD_PICK, count=1,
           pattern=[[GOLD_INGOT, GOLD_INGOT, GOLD_INGOT],
                    [AIR,        STICK,       AIR       ],
                    [AIR,        STICK,       AIR       ]]),

    # ── Glass ────────────────────────────────────────────────────────────────
    # (smelted from sand — handled by furnace, but also here as shapeless)
    Recipe(result=GLASS, count=1,
           ingredients=[SAND]),

]


# ── Matching logic ────────────────────────────────────────────────────────────

def _normalise_grid(grid: list[list[int]]) -> list[list[int]]:
    """Strip empty rows/columns from the edges of a crafting grid."""
    # Remove empty rows top/bottom
    while grid and all(c == AIR for c in grid[0]):
        grid = grid[1:]
    while grid and all(c == AIR for c in grid[-1]):
        grid = grid[:-1]
    if not grid:
        return []
    # Remove empty columns left/right
    cols = len(grid[0])
    left  = next((c for c in range(cols)
                  if any(row[c] != AIR for row in grid)), cols)
    right = next((c for c in range(cols - 1, -1, -1)
                  if any(row[c] != AIR for row in grid)), -1)
    if left > right:
        return []
    return [[row[c] for c in range(left, right + 1)] for row in grid]


def match_recipe(grid: list[list[int]]) -> Optional[Recipe]:
    """
    Given a crafting grid (list of rows, each a list of item IDs),
    return the matching Recipe or None.
    """
    norm = _normalise_grid([list(row) for row in grid])

    # Collect non-air items for shapeless check
    items_in_grid = sorted(
        item for row in grid for item in row if item != AIR
    )

    for recipe in RECIPES:
        if recipe.is_shapeless:
            if sorted(recipe.ingredients) == items_in_grid:
                return recipe
        else:
            # Shaped: try direct and horizontally flipped
            for pat in [recipe.pattern, _hflip(recipe.pattern)]:
                if _grids_match(norm, pat):
                    return recipe
    return None


def _hflip(pattern: list[list[int]]) -> list[list[int]]:
    return [list(reversed(row)) for row in pattern]


def _grids_match(a: list[list[int]], b: list[list[int]]) -> bool:
    if len(a) != len(b):
        return False
    for ra, rb in zip(a, b):
        if len(ra) != len(rb):
            return False
        for ca, cb in zip(ra, rb):
            if ca != cb:
                return False
    return True


# ── Smelting ─────────────────────────────────────────────────────────────────

SMELT_RECIPES: dict[int, tuple[int, int]] = {
    # input → (output, ticks_to_smelt at 60fps)
    IRON_ORE:  (IRON_INGOT, 200),
    GOLD_ORE:  (GOLD_INGOT, 300),
    SAND:      (GLASS,      180),
    CLAY:      (STONE,      150),
}


def smelt(input_item: int) -> Optional[tuple[int, int]]:
    """Return (output_item, ticks) or None if not smeltable."""
    return SMELT_RECIPES.get(input_item)


# ── Ore drops ─────────────────────────────────────────────────────────────────

ORE_DROPS: dict[int, int] = {
    COAL_ORE: COAL,
    IRON_ORE: IRON_ORE,   # raw ore (must smelt)
    GOLD_ORE: GOLD_ORE,
}
