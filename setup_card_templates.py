"""
setup_card_templates.py
Run once on the VPS to populate C:\\templates\\cards\\ with named card icon PNGs.

Usage:
    python C:\\setup_card_templates.py

It walks C:\\TKH and C:\\py-clash-bot looking for PNG files whose names
fuzzy-match a Clash Royale card name, then copies them (renamed) to
C:\\templates\\cards\\<Card Name>.png.

After running, check the printed report for cards that were NOT found —
those you'll need to crop manually from the game's card collection screen.
"""

import os
import re
import shutil

SEARCH_DIRS = [r"C:\TKH", r"C:\py-clash-bot"]
OUT_DIR     = r"C:\templates\cards"

# All card names the bot knows about (keep in sync with CARD_TYPES in the bot).
CARD_NAMES = [
    # Tanks
    "Giant", "Golem", "P.E.K.K.A", "Giant Skeleton", "Lava Hound",
    "Royal Giant", "Balloon",
    # Mini tanks
    "Knight", "Valkyrie", "Mini P.E.K.K.A", "Dark Prince", "Ice Golem",
    "Guards", "Barbarians",
    # Win conditions
    "Hog Rider", "Miner", "Goblin Barrel", "Three Musketeers",
    # Support
    "Musketeer", "Witch", "Electro Wizard", "Baby Dragon", "Mega Minion",
    "Bomber", "Executioner", "Bowler", "Prince", "Lumberjack",
    # Cycle
    "Skeleton Army", "Goblin Gang", "Minion Horde", "Bats",
    # Spells (small)
    "Ice Spirit", "Electro Spirit", "Fire Spirit", "Zap", "Skeleton",
    "Log", "Tornado", "Earthquake", "Giant Snowball",
    # Spells (big)
    "Fireball", "Rocket", "Arrows", "Lightning", "Freeze", "Poison", "Clone",
    # Buildings
    "Tesla", "Cannon", "Inferno Tower", "Bomb Tower", "X-Bow", "Mortar",
    "Furnace", "Goblin Cage", "Elixir Collector", "Goblin Hut",
    "Tombstone", "Barbarian Hut",
    # Air support
    "Minions", "Inferno Dragon", "Electro Dragon",
]


def _slug(s: str) -> str:
    """Lower-case, strip all non-alphanumeric."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _build_slug_map():
    """
    For each card name, generate several slug variants that might appear in
    filenames from different asset repos.
    Returns dict: slug -> canonical card name
    """
    m = {}
    for name in CARD_NAMES:
        base = _slug(name)
        m[base] = name
        # Common prefix patterns in asset repos
        m["card" + base]      = name
        m["icon" + base]      = name
        m["iconcard" + base]  = name
        m["cardicon" + base]  = name
        m[base + "card"]      = name
        m[base + "icon"]      = name
    return m


def _collect_pngs():
    """Walk all search dirs and return list of absolute PNG paths."""
    pngs = []
    for root_dir in SEARCH_DIRS:
        if not os.path.isdir(root_dir):
            print(f"[skip] {root_dir} not found")
            continue
        for dirpath, _dirs, files in os.walk(root_dir):
            for fname in files:
                if fname.lower().endswith(".png"):
                    pngs.append(os.path.join(dirpath, fname))
    return pngs


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    slug_map   = _build_slug_map()
    all_pngs   = _collect_pngs()
    print(f"\nFound {len(all_pngs)} PNG files across search dirs.\n")

    matched   = {}  # card_name -> source path (first match wins)
    unmatched = []  # paths that didn't map to any card

    for path in all_pngs:
        fname = os.path.splitext(os.path.basename(path))[0]
        key   = _slug(fname)
        card  = slug_map.get(key)
        if card:
            if card not in matched:
                matched[card] = path
        else:
            unmatched.append(path)

    # Copy matched files
    print("── Matched cards ──────────────────────────────")
    for card, src in sorted(matched.items()):
        dst = os.path.join(OUT_DIR, card + ".png")
        shutil.copy2(src, dst)
        print(f"  ✓  {card:30s}  ←  {os.path.basename(src)}")

    # Report missing cards
    missing = [n for n in CARD_NAMES if n not in matched]
    print(f"\n── Missing ({len(missing)}) ──────────────────────────────")
    for n in missing:
        print(f"  ✗  {n}")

    print(f"\n── Summary ───────────────────────────────────")
    print(f"  Copied  : {len(matched)}/{len(CARD_NAMES)}")
    print(f"  Missing : {len(missing)}")
    print(f"  Output  : {OUT_DIR}")
    if missing:
        print("\nFor missing cards: open the card collection screen in-game,")
        print("run capture_screens.py, crop each card icon in Paint, and save")
        print(f"to {OUT_DIR}\\<Card Name>.png  (exact name, case-sensitive).")


if __name__ == "__main__":
    main()
