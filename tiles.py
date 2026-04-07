"""
Block type definitions and tile atlas mappings for The Blockheads PC.

The tile atlas (TileMap.png) is 2048x2048 with a 32x32 grid of tiles,
each tile being 64x64 pixels. Positions are given as (col, row).
"""

# ── Block type IDs ──────────────────────────────────────────────────────────
AIR        =  0
STONE      =  1
DIRT       =  2
GRASS      =  3
SAND       =  4
WATER      =  5
GRAVEL     =  6
WOOD       =  7   # tree log / trunk
LEAVES     =  8
COAL_ORE   =  9
IRON_ORE   = 10
GOLD_ORE   = 11
LAVA       = 12
LIMESTONE  = 13
MARBLE     = 14
SNOW       = 15
ICE        = 16
LADDER     = 17
FLINT      = 18

# ── Tile atlas positions (col, row) in the 32×32 grid ──────────────────────
# Each tile is 64px × 64px in the 2048×2048 TileMap.png
BLOCK_ATLAS: dict[int, tuple[int, int] | None] = {
    AIR:       None,
    STONE:     (3,  0),   # bluish-gray stone
    DIRT:      (0,  2),   # warm brown dirt
    GRASS:     (8,  7),   # green-topped dirt
    SAND:      (28, 2),   # yellowish tan
    WATER:     (14, 0),   # blue water (semi-transparent in atlas)
    GRAVEL:    (2,  0),   # dark gravel
    WOOD:      (0,  4),   # tree bark / log
    LEAVES:    (0,  5),   # green leaves
    COAL_ORE:  (1,  0),   # dark stone with coal
    IRON_ORE:  (5,  6),   # stone with iron veins
    GOLD_ORE:  (21, 2),   # golden stone
    LAVA:      (12, 0),   # hot orange
    LIMESTONE: (14, 2),   # light gray limestone
    MARBLE:    (11, 2),   # white marble
    SNOW:      (4,  6),   # snowy white
    ICE:       (27, 7),   # icy blue
    LADDER:    (2,  4),   # wooden ladder
    FLINT:     (15, 2),   # dark flint stone
}

# ── Block properties ─────────────────────────────────────────────────────────

# Blocks that physically stop movement
SOLID_BLOCKS = {
    STONE, DIRT, GRASS, SAND, GRAVEL, WOOD, LEAVES,
    COAL_ORE, IRON_ORE, GOLD_ORE, LIMESTONE, MARBLE, SNOW, ICE, FLINT, LADDER,
}

# Blocks that slow but don't stop movement
LIQUID_BLOCKS = {WATER, LAVA}

# Blocks that light passes through (no shadow cast)
TRANSPARENT_BLOCKS = {AIR, WATER, LAVA, LEAVES}

# Mining time in frames (at 60 fps) – 0 means instant / unminable
BLOCK_HARDNESS: dict[int, int] = {
    AIR:       0,
    STONE:     120,
    DIRT:      40,
    GRASS:     45,
    SAND:      30,
    WATER:     0,
    GRAVEL:    50,
    WOOD:      80,
    LEAVES:    10,
    COAL_ORE:  150,
    IRON_ORE:  220,
    GOLD_ORE:  300,
    LAVA:      0,
    LIMESTONE: 100,
    MARBLE:    90,
    SNOW:      20,
    ICE:       60,
    LADDER:    30,
    FLINT:     80,
}

# Display names
BLOCK_NAMES: dict[int, str] = {
    AIR:       "Air",
    STONE:     "Stone",
    DIRT:      "Dirt",
    GRASS:     "Grass",
    SAND:      "Sand",
    WATER:     "Water",
    GRAVEL:    "Gravel",
    WOOD:      "Wood",
    LEAVES:    "Leaves",
    COAL_ORE:  "Coal Ore",
    IRON_ORE:  "Iron Ore",
    GOLD_ORE:  "Gold Ore",
    LAVA:      "Lava",
    LIMESTONE: "Limestone",
    MARBLE:    "Marble",
    SNOW:      "Snow",
    ICE:       "Ice",
    LADDER:    "Ladder",
    FLINT:     "Flint",
}

# Hotbar default loadout (shown in creative mode)
HOTBAR_DEFAULTS = [
    DIRT, STONE, SAND, GRAVEL, WOOD, LEAVES, LIMESTONE, MARBLE, FLINT,
]

# Drop (item returned when mined)
BLOCK_DROP: dict[int, int] = {
    GRASS: DIRT,
    LEAVES: LEAVES,  # chance-based in original; always drop here
}
