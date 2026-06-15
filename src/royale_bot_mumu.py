import cv2
import numpy as np
import time
import random
import requests
import subprocess
import json
import os
from collections import deque
from PIL import Image
from datetime import datetime, timezone
import io
import threading

# ─── CONFIG ──────────────────────────────────────────────────────────────────
WORKER_URL   = "https://small-king-a65c.jared1999.workers.dev"
ADB          = r"C:\adb\platform-tools\adb.exe"
DEVICE       = "127.0.0.1:7555"
REPLAY_DIR   = r"C:\royale_replays"

# ─── DEBUG FLAGS ─────────────────────────────────────────────────────────────
DEBUG             = True
DEBUG_FORCE_PLAY  = True
DEBUG_NO_JITTER   = True
DEBUG_SAVE_COORDS = True
BATTLE_DEBOUNCE   = 1

# ─── PLAYER CONFIG ───────────────────────────────────────────────────────────
# Your Clash Royale player tag WITHOUT the leading #.
# e.g. if your tag is #ABC123, set PLAYER_TAG = "ABC123"
PLAYER_TAG = ""

# ─── CARD TYPE REGISTRY (10 categories) ─────────────────────────────────────
CARD_TYPES = {
    # Tanks — high HP, slow, anchor pushes
    "Giant": "tank", "Golem": "tank", "P.E.K.K.A": "tank",
    "Giant Skeleton": "tank", "Lava Hound": "tank", "Royal Giant": "tank",
    "Balloon": "tank",
    # Mini tanks — moderate HP, defensive backbone
    "Knight": "mini_tank", "Valkyrie": "mini_tank", "Mini P.E.K.K.A": "mini_tank",
    "Dark Prince": "mini_tank", "Ice Golem": "mini_tank", "Guards": "mini_tank",
    "Barbarians": "mini_tank",
    # Win conditions — primary damage dealers
    "Hog Rider": "win_condition", "Miner": "win_condition",
    "Goblin Barrel": "win_condition", "Three Musketeers": "win_condition",
    # Support — ranged/splash behind push
    "Musketeer": "support", "Witch": "support", "Electro Wizard": "support",
    "Baby Dragon": "support", "Mega Minion": "support", "Bomber": "support",
    "Executioner": "support", "Bowler": "support", "Prince": "support",
    "Lumberjack": "support",
    # Cycle — cheap fast cards, keep rotation moving
    "Ice Spirit": "cycle", "Skeletons": "cycle", "Bats": "cycle",
    "Goblin": "cycle", "Goblin Gang": "cycle",
    # Small spells — cheap utility/clear
    "Zap": "spell_small", "Arrows": "spell_small", "Log": "spell_small",
    "Freeze": "spell_small", "Tornado": "spell_small", "Earthquake": "spell_small",
    "Giant Snowball": "spell_small",
    # Big spells — high damage, need a target clump
    "Fireball": "spell_big", "Lightning": "spell_big", "Rocket": "spell_big",
    "Poison": "spell_big", "Clone": "spell_big",
    # Buildings — defensive structures
    "Tesla": "building", "Cannon": "building", "Inferno Tower": "building",
    "Bomb Tower": "building", "X-Bow": "building", "Mortar": "building",
    "Furnace": "building", "Goblin Cage": "building", "Elixir Collector": "building",
    # Air support — flying units
    "Minion Horde": "air_support", "Minions": "air_support",
    "Skeleton Army": "air_support", "Inferno Dragon": "air_support",
    "Electro Dragon": "air_support",
}

# Cards that behave like troops for placement purposes
_TROOP_LIKE = {"tank", "mini_tank", "win_condition", "support", "cycle", "air_support"}
# Cards that are spells
_SPELL_LIKE = {"spell_small", "spell_big"}

def card_type(card_name):
    return CARD_TYPES.get(card_name, "mini_tank")

# ─── SPELL RADII (proportional arena width) ──────────────────────────────────
SPELL_RADII = {
    "Fireball": 0.15, "Poison": 0.18, "Rocket": 0.10, "Lightning": 0.13,
    "Clone": 0.16, "Freeze": 0.16, "Arrows": 0.20, "Zap": 0.10,
    "Log": 0.08, "Tornado": 0.14, "Earthquake": 0.18, "Giant Snowball": 0.12,
}
_DEFAULT_SPELL_RADIUS = 0.12

def spell_target_value(card_name, tx_norm, ty_norm, troops):
    """Count troops within this spell's radius. Used to gate casting."""
    r = SPELL_RADII.get(card_name, _DEFAULT_SPELL_RADIUS)
    return sum(
        1 for t in troops
        if ((t["x_norm"] - tx_norm) ** 2 + (t["y_norm"] - ty_norm) ** 2) ** 0.5 <= r
    )

# ─── OPPONENT ARCHETYPE SIGNALS ──────────────────────────────────────────────
_ARCHETYPE_SIGNALS = {
    "beatdown":    ["Giant", "Golem", "P.E.K.K.A", "Giant Skeleton", "Lava Hound",
                    "Royal Giant", "Balloon"],
    "cycle":       ["Ice Spirit", "Skeletons", "Ice Golem", "Bats", "Log"],
    "control":     ["X-Bow", "Mortar", "Tesla", "Inferno Tower", "Cannon"],
    "bridge_spam": ["Battle Ram", "Bandit", "Dark Prince", "Goblin Gang"],
    "log_bait":    ["Goblin Barrel", "Princess", "Dart Goblin", "Goblin Gang"],
    "three_m":     ["Three Musketeers", "Elixir Collector"],
}

# ─── DECK FETCHER ─────────────────────────────────────────────────────────────
_SLOT_FALLBACK = [f"slot_{i}" for i in range(8)]

def fetch_deck():
    """
    Fetch the player's current deck from the worker API.
    Returns a list of 8 card-name strings.
    Falls back to slot placeholders if the tag is unset or the request fails.
    """
    if not PLAYER_TAG:
        print("[deck] PLAYER_TAG not set — using slot placeholders")
        return list(_SLOT_FALLBACK)
    try:
        url  = f"{WORKER_URL}/v1/players/%23{PLAYER_TAG}"
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        cards = resp.json().get("currentDeck", [])
        names = [c["name"] for c in cards]
        if len(names) == 8:
            print(f"[deck] Fetched: {names}")
            return names
        print(f"[deck] Unexpected deck length ({len(names)}) — using placeholders")
    except Exception as e:
        print(f"[deck] Fetch failed ({e}) — using placeholders")
    return list(_SLOT_FALLBACK)

# ─── NAMED TILE MAP ──────────────────────────────────────────────────────────
# (x_frac, y_frac); y < 0.50 = opponent territory, y > 0.50 = own territory
TILES = {
    "bridge_left":      (0.22, 0.54),
    "bridge_right":     (0.78, 0.54),
    "bridge_center":    (0.50, 0.54),
    "support_left":     (0.22, 0.63),
    "support_right":    (0.78, 0.63),
    "support_center":   (0.50, 0.63),
    "defense_left":     (0.22, 0.74),
    "defense_right":    (0.78, 0.74),
    "defense_center":   (0.50, 0.72),
    "push_left":        (0.22, 0.44),
    "push_right":       (0.78, 0.44),
    "push_center":      (0.50, 0.44),
    "spell_left":       (0.22, 0.42),
    "spell_right":      (0.78, 0.42),
    "spell_center":     (0.50, 0.42),
    "anti_hog_left":    (0.20, 0.72),
    "anti_hog_right":   (0.80, 0.72),
    "king_activate":    (0.50, 0.80),
    "safe_building_l":  (0.18, 0.76),
    "safe_building_r":  (0.82, 0.76),
}

ARENA_X_MIN, ARENA_X_MAX = 0.05, 0.95
ARENA_Y_MIN, ARENA_Y_MAX = 0.15, 0.80

# ─── BATTLE PHASES ───────────────────────────────────────────────────────────
PHASE_OPENING    = "opening"     # 0 – 30 s
PHASE_MID        = "mid"         # 30 – 90 s
PHASE_DOUBLE     = "double"      # 90 – 120 s
PHASE_OVERTIME   = "overtime"    # 120 s +
PHASE_DEFENDING  = "defending"   # triggered by enemy push
PHASE_COUNTERPUSH = "counterpush" # triggered after successful defense

# ─── HUMAN TIMING MODEL (#13) ────────────────────────────────────────────────
# Sampled from replay data of human play intervals.
# Until enough replays are collected these are reasonable approximations.
_TIMING_INTERVALS = [0.4, 0.8, 1.2, 1.5, 2.0, 2.5, 3.0, 3.5, 4.5, 6.0]
_TIMING_WEIGHTS   = [0.04, 0.10, 0.18, 0.22, 0.20, 0.12, 0.07, 0.04, 0.02, 0.01]

def human_play_interval(phase=None):
    """Play-cooldown from human-like distribution, capped by phase."""
    base = random.choices(_TIMING_INTERVALS, weights=_TIMING_WEIGHTS, k=1)[0]
    if phase in (PHASE_DOUBLE, PHASE_OVERTIME):
        return min(base, 1.5)    # double elixir: max 1.5 s
    elif phase == PHASE_OPENING:
        return min(base, 2.5)    # opening: max 2.5 s
    return min(base, 3.5)        # mid / other: max 3.5 s

# ─── ENEMY ELIXIR TRACKER (#2) ───────────────────────────────────────────────
class EnemyElixirTracker:
    """
    Rule-based estimate of opponent's current elixir.
    Regenerates at 1 per 2.8 s (normal) or 1 per 1.4 s (double-elixir).
    Call .update(is_double) every loop. Call .spent(cost) when a card is detected.
    """
    REGEN_NORMAL = 2.8
    REGEN_DOUBLE = 1.4

    def __init__(self):
        self.estimate  = 5.0
        self._last_t   = time.time()

    def update(self, is_double=False):
        now     = time.time()
        elapsed = now - self._last_t
        rate    = self.REGEN_DOUBLE if is_double else self.REGEN_NORMAL
        self.estimate = min(10.0, self.estimate + elapsed / rate)
        self._last_t  = now

    def spent(self, cost):
        """Call when we observe the opponent playing a card of known cost."""
        self.estimate = max(0.0, self.estimate - cost)

    @property
    def is_low(self):
        return self.estimate < 4

    @property
    def is_high(self):
        return self.estimate >= 7

# ─── CARD ROTATION TRACKER (#3) ──────────────────────────────────────────────
class CardRotation:
    """
    Simulates Clash Royale's 8-card cycle with a deque.
    hand[0..3]  = currently visible slots
    draw_pile   = the next 4 cards waiting to come in

    When slot S is played:
      - the played card goes to the back of draw_pile
      - the front of draw_pile slides into hand[S]
    """
    def __init__(self, deck):
        self._hand      = deque(deck[:4])
        self._draw_pile = deque(deck[4:])

    def play(self, slot):
        """Play card at slot; returns card name played."""
        played = self._hand[slot]
        if self._draw_pile:
            self._hand[slot] = self._draw_pile.popleft()
            self._draw_pile.append(played)
        return played

    def card_at(self, slot):
        return self._hand[slot]

    @property
    def hand(self):
        return list(self._hand)

# ─── LANE PRESSURE TRACKER (#5) ──────────────────────────────────────────────
class LanePressureTracker:
    """
    Scores 0-100 danger on each lane, based on tower HP rate of change.
    A lane whose tower is losing HP quickly is under threat.
    """
    def __init__(self):
        self.left  = 0.0
        self.right = 0.0
        self._prev_hp = {}
        self._last_t  = time.time()

    def update(self, tower_hp: dict):
        now     = time.time()
        elapsed = max(0.1, now - self._last_t)

        def delta(key):
            prev = self._prev_hp.get(key, tower_hp.get(key, 100))
            curr = tower_hp.get(key, 100)
            return max(0.0, (prev - curr) / elapsed)   # HP lost per second

        left_threat  = delta("our_left")  * 8
        right_threat = delta("our_right") * 8

        # Exponential decay + new threat
        decay = max(0.0, 1.0 - elapsed * 0.15)
        self.left  = min(100.0, self.left  * decay + left_threat)
        self.right = min(100.0, self.right * decay + right_threat)

        self._prev_hp = dict(tower_hp)
        self._last_t  = now

    @property
    def hot_lane(self):
        if self.left > 20 or self.right > 20:
            return "left" if self.left >= self.right else "right"
        return None

    @property
    def under_attack(self):
        return self.left > 30 or self.right > 30

# ─── BATTLE STATE MACHINE (#1) ───────────────────────────────────────────────
class BattleStateMachine:
    """
    Drives battle phase transitions.
    Phases affect tile pool selection and spell targeting.
    """
    def __init__(self):
        self.phase      = PHASE_OPENING
        self._defend_t  = None

    def update(self, game_time, lane_pressure: LanePressureTracker):
        # Time-based baseline
        if game_time < 30:
            base = PHASE_OPENING
        elif game_time < 90:
            base = PHASE_MID
        elif game_time < 120:
            base = PHASE_DOUBLE
        else:
            base = PHASE_OVERTIME

        # Override: switch to defending if lane under attack
        if lane_pressure.under_attack:
            if self.phase != PHASE_DEFENDING:
                self._defend_t = time.time()
            self.phase = PHASE_DEFENDING
            return

        # Counterpush window: 8 s after danger subsides
        if self.phase == PHASE_DEFENDING and self._defend_t:
            if time.time() - self._defend_t < 8:
                self.phase = PHASE_COUNTERPUSH
                return
            self._defend_t = None

        self.phase = base

    @property
    def is_double(self):
        return self.phase in (PHASE_DOUBLE, PHASE_OVERTIME)

# ─── CARD-SPECIFIC PLACEMENT HANDLERS (#8) ───────────────────────────────────

def _tile(name, w, h):
    px, py = TILES[name]
    jx = 0 if DEBUG_NO_JITTER else random.randint(-10, 10)
    jy = 0 if DEBUG_NO_JITTER else random.randint(-8,   8)
    x = int(px * w) + jx
    y = int(py * h) + jy
    x = max(int(ARENA_X_MIN * w), min(int(ARENA_X_MAX * w), x))
    y = max(int(ARENA_Y_MIN * h), min(int(ARENA_Y_MAX * h), y))
    return x, y, name   # (px, py, tile_name)

def place_troop(card_name, phase, lane: LanePressureTracker, w, h):
    """Place troop with type-aware and phase-aware tile selection."""
    ctype = card_type(card_name)

    if phase == PHASE_DEFENDING and lane.hot_lane:
        pool = (["defense_left", "support_left"] if lane.hot_lane == "left"
                else ["defense_right", "support_right"])
    elif ctype == "win_condition":
        # Win conditions always go to bridge regardless of phase
        if lane.hot_lane:
            pool = (["bridge_left"] if lane.hot_lane == "left" else ["bridge_right"])
        else:
            pool = ["bridge_left", "bridge_right"]
    elif ctype == "tank" and phase == PHASE_OPENING:
        # Don't rush a tank at the start — place it back for a safe push
        pool = ["support_left", "support_right"]
    elif phase == PHASE_COUNTERPUSH and lane.hot_lane:
        pool = (["bridge_left", "push_left"] if lane.hot_lane == "left"
                else ["bridge_right", "push_right"])
    elif phase in (PHASE_DOUBLE, PHASE_OVERTIME):
        pool = ["push_left", "push_right", "bridge_left", "bridge_right",
                "bridge_center"]
    elif phase == PHASE_MID:
        pool = ["bridge_left", "bridge_right", "bridge_center",
                "support_left", "support_right"]
    else:  # opening
        if ctype == "cycle":
            pool = ["bridge_left", "bridge_right"]   # cheap cards can go bridge early
        else:
            pool = ["support_left", "support_right", "support_center",
                    "bridge_left", "bridge_right"]
    return _tile(random.choice(pool), w, h)

def place_building(card_name, phase, lane: LanePressureTracker, w, h):
    """Buildings go on defensive tiles; mirror hot lane if under attack."""
    if lane.hot_lane == "left":
        pool = ["anti_hog_left", "defense_left", "safe_building_l"]
    elif lane.hot_lane == "right":
        pool = ["anti_hog_right", "defense_right", "safe_building_r"]
    else:
        pool = ["defense_left", "defense_right", "defense_center",
                "safe_building_l", "safe_building_r"]
    return _tile(random.choice(pool), w, h)

def place_spell(card_name, phase, lane: LanePressureTracker, game_time, w, h,
                troops=None):
    """
    Spells target enemy territory, preferring the hot lane.
    Gates on spell_target_value when troops are detected:
      spell_big  requires ≥1 troop in radius
      spell_small requires ≥3 troops in radius (not worth a small spell on 1 unit)
    Returns None to hold the card.
    """
    if game_time < 20:
        return None

    if lane.hot_lane == "left":
        pool = ["spell_left", "push_left"]
    elif lane.hot_lane == "right":
        pool = ["spell_right", "push_right"]
    else:
        pool = ["spell_left", "spell_right", "spell_center"]

    x, y, name = _tile(random.choice(pool), w, h)

    if troops:
        tx_n, ty_n = x / w, y / h
        value = spell_target_value(card_name, tx_n, ty_n, troops)
        min_hit = 1 if card_type(card_name) == "spell_big" else 3
        if value < min_hit:
            return None   # not enough targets — hold it

    return x, y, name

def get_play_position(card_name, phase, lane_pressure, game_time, w, h, troops=None):
    """
    Returns (x, y, tile_name) or None (meaning: hold this card).
    Tries PLACEMENT_DB learned distribution first; falls back to heuristics.
    """
    lane  = lane_pressure.hot_lane or "center"
    ctype = card_type(card_name)

    learned = PLACEMENT_DB.sample_placement(card_name, phase, lane)
    if learned:
        x_n, y_n = learned
        if DEBUG:
            print(f"  [DB] {card_name} → learned ({x_n:.3f},{y_n:.3f})")
        return int(x_n * w), int(y_n * h), "learned"

    if ctype in _TROOP_LIKE:
        return place_troop(card_name, phase, lane_pressure, w, h)
    elif ctype == "building":
        return place_building(card_name, phase, lane_pressure, w, h)
    elif ctype in _SPELL_LIKE:
        return place_spell(card_name, phase, lane_pressure, game_time, w, h, troops)
    return place_troop(card_name, phase, lane_pressure, w, h)

# ─── PLACEMENT DATABASE ───────────────────────────────────────────────────────

class PlacementDB:
    """
    Accumulates win-weighted (card, phase, lane) → [(x, y, won)] across battles.
    Once MIN_SAMPLES entries exist for a key, sample_placement() replaces heuristics.
    Persists as JSON at REPLAY_DIR/placement_db.json.
    """
    MIN_SAMPLES = 20

    def __init__(self):
        self._data = {}   # key → [[x_norm, y_norm, won_int], ...]
        self._path = os.path.join(REPLAY_DIR, "placement_db.json")
        self._load()

    def _load(self):
        try:
            with open(self._path) as f:
                self._data = json.load(f)
            total = sum(len(v) for v in self._data.values())
            print(f"[PlacementDB] Loaded {total} entries across {len(self._data)} keys")
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[PlacementDB] Load error: {e}")

    def save(self):
        os.makedirs(REPLAY_DIR, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._data, f)

    def record(self, card, phase, lane, x_norm, y_norm, won):
        key = f"{card}|{phase}|{lane}"
        if key not in self._data:
            self._data[key] = []
        self._data[key].append([round(x_norm, 3), round(y_norm, 3), int(won)])

    def sample_placement(self, card, phase, lane):
        """
        Win-weighted sample from historical placements.
        Won placements get 2× weight over losses.
        Returns (x_norm, y_norm) or None when data is insufficient.
        """
        key     = f"{card}|{phase}|{lane}"
        entries = self._data.get(key, [])
        if len(entries) < self.MIN_SAMPLES:
            return None
        weights = [2 if e[2] else 1 for e in entries]
        e = random.choices(entries, weights=weights, k=1)[0]
        return e[0], e[1]

    def summary(self):
        """Return {key: sample_count} for keys that have reached MIN_SAMPLES."""
        return {k: len(v) for k, v in self._data.items()
                if len(v) >= self.MIN_SAMPLES}

PLACEMENT_DB = PlacementDB()

# ─── TROOP DETECTOR (#1) ─────────────────────────────────────────────────────

class TroopDetector:
    """
    Detects moving units in the arena via frame differencing.
    Returns list of {"x_norm", "y_norm"} blobs — positions only, no card names.
    Used for: spell value calculation, battlefield awareness.
    """
    _ARENA_Y0    = 0.15
    _ARENA_Y1    = 0.85
    _MIN_AREA    = 150    # px² — ignore tiny noise blobs
    _DIFF_THRESH = 20     # pixel diff threshold

    def __init__(self):
        self._prev = None

    def detect(self, screen):
        h, w = screen.shape[:2]
        arena = screen[int(h * self._ARENA_Y0):int(h * self._ARENA_Y1), :]
        gray  = cv2.cvtColor(arena, cv2.COLOR_BGR2GRAY)
        gray  = cv2.GaussianBlur(gray, (5, 5), 0)

        if self._prev is None or self._prev.shape != gray.shape:
            self._prev = gray
            return []

        diff   = cv2.absdiff(self._prev, gray)
        _, thr = cv2.threshold(diff, self._DIFF_THRESH, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        thr    = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, kernel)
        self._prev = gray

        ay0 = int(h * self._ARENA_Y0)
        troops = []
        for c in cv2.findContours(thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
            if cv2.contourArea(c) < self._MIN_AREA:
                continue
            M = cv2.moments(c)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"]) + ay0
            troops.append({"x_norm": round(cx / w, 3), "y_norm": round(cy / h, 3)})
        return troops

# ─── WAIT DB (#4) ────────────────────────────────────────────────────────────

class WaitDB:
    """
    Learns waiting durations per phase from historical wait_events.
    Once MIN_SAMPLES exist, sample_wait() replaces human_play_interval().
    """
    MIN_SAMPLES = 25

    def __init__(self):
        self._data = {}   # phase → [duration_s, ...]
        self._path = os.path.join(REPLAY_DIR, "wait_db.json")
        self._load()

    def _load(self):
        try:
            with open(self._path) as f:
                self._data = json.load(f)
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[WaitDB] Load error: {e}")

    def save(self):
        os.makedirs(REPLAY_DIR, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._data, f)

    def record_battle(self, wait_events):
        for ev in wait_events:
            ms = ev.get("duration_ms", 0)
            if ms < 200:
                continue   # ignore sub-200ms noise
            phase = ev.get("phase", "mid")
            self._data.setdefault(phase, []).append(round(ms / 1000.0, 2))

    def sample_wait(self, phase):
        entries = self._data.get(phase, [])
        if len(entries) < self.MIN_SAMPLES:
            return None
        return random.choice(entries)

# ─── COMBO TRACKER (#5) ──────────────────────────────────────────────────────

class ComboTracker:
    """
    Tracks (prev_card, card, phase) → win-rate to learn effective sequences.
    score_follow_up() returns a 0-1 quality score for a card given the previous.
    """
    MIN_SAMPLES = 10

    def __init__(self):
        self._data = {}   # key → {"wins": N, "total": N}
        self._path = os.path.join(REPLAY_DIR, "combo_db.json")
        self._load()

    def _load(self):
        try:
            with open(self._path) as f:
                self._data = json.load(f)
        except FileNotFoundError:
            pass

    def save(self):
        os.makedirs(REPLAY_DIR, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._data, f)

    def record(self, prev_card, card, phase, won):
        key = f"{prev_card}|{card}|{phase}"
        e   = self._data.setdefault(key, {"wins": 0, "total": 0})
        e["total"] += 1
        if won:
            e["wins"] += 1

    def score_follow_up(self, prev_card, card, phase):
        """Win rate 0-1, or 0.5 when insufficient data."""
        e = self._data.get(f"{prev_card}|{card}|{phase}")
        if not e or e["total"] < self.MIN_SAMPLES:
            return 0.5
        return e["wins"] / e["total"]

# ─── ARCHETYPE DETECTOR (#6) ─────────────────────────────────────────────────

class ArchetypeDetector:
    """
    Classifies opponent deck archetype from observed cards.
    Scaffold: call .observe(card_name) when visual detection lands.
    """
    def __init__(self):
        self.seen = set()

    def observe(self, card_name):
        self.seen.add(card_name)

    @property
    def archetype(self):
        scores = {arch: sum(1 for c in cards if c in self.seen)
                  for arch, cards in _ARCHETYPE_SIGNALS.items()}
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "unknown"

    @property
    def should_rush(self):
        return self.archetype in ("log_bait", "three_m")

    @property
    def should_defend(self):
        return self.archetype in ("beatdown", "bridge_spam")

# ─── OPPONENT CYCLE TRACKER (#7) ─────────────────────────────────────────────

class OpponentCycleTracker:
    """
    Tracks opponent cards played in order.
    Once 4 unique cards are seen, cycle repeats and likely_next() works.
    Scaffold: call .observe(card_name) from visual card detection when ready.
    """
    def __init__(self):
        self._log    = []   # all plays in order
        self._unique = []   # unique cards in first-seen order

    def observe(self, card_name):
        self._log.append(card_name)
        if card_name not in self._unique:
            self._unique.append(card_name)

    def likely_next(self):
        if len(self._unique) < 4:
            return None
        pos = len(self._log) % len(self._unique)
        return self._unique[pos]

    @property
    def cards_seen(self):
        return list(self._unique)

WAIT_DB  = WaitDB()
COMBO_DB = ComboTracker()

# ─── ADB CONTROLLER ──────────────────────────────────────────────────────────


def adb_cmd(cmd_list):
    return subprocess.run([ADB, "-s", DEVICE] + cmd_list, capture_output=True)

def _jitter():
    return (0, 0) if DEBUG_NO_JITTER else (random.randint(-3, 3), random.randint(-3, 3))

def tap(x, y):
    jx, jy = _jitter()
    adb_cmd(["shell", "input", "tap", str(x + jx), str(y + jy)])
    time.sleep(random.uniform(0.05, 0.15))

def drag(x1, y1, x2, y2, duration_ms=150):
    jx, jy = _jitter()
    adb_cmd([
        "shell", "input", "swipe",
        str(x1 + jx), str(y1 + jy),
        str(x2), str(y2),
        str(duration_ms),
    ])
    time.sleep(random.uniform(0.08, 0.18))

def screenshot():
    result = adb_cmd(["exec-out", "screencap", "-p"])
    img = Image.open(io.BytesIO(result.stdout))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

def save_screenshot(path=r"C:\debug_screen.png"):
    result = adb_cmd(["exec-out", "screencap", "-p"])
    with open(path, "wb") as f:
        f.write(result.stdout)
    print(f"Screenshot saved to {path}")

def key_event(keycode):
    adb_cmd(["shell", "input", "keyevent", str(keycode)])

# ─── DEBUG: coordinate overlay ───────────────────────────────────────────────

def save_coord_overlay(screen, card_positions, path=r"C:\debug_coords.png"):
    img = screen.copy()
    h, w = img.shape[:2]
    for idx, (cx, cy) in card_positions.items():
        cv2.circle(img, (cx, cy), 18, (0, 255, 0), 3)
        cv2.putText(img, f"C{idx}", (cx - 12, cy - 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    for name, (px, py) in TILES.items():
        tx, ty = int(px * w), int(py * h)
        cv2.circle(img, (tx, ty), 8, (0, 0, 255), 2)
        cv2.putText(img, name[:8], (tx - 20, ty - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 200, 255), 1)
    cv2.imwrite(path, img)
    print(f"Coord overlay saved to {path}")

# ─── SCREEN DETECTION ────────────────────────────────────────────────────────

def is_on_home_screen(screen):
    h, w = screen.shape[:2]
    region = screen[int(h * 0.65):int(h * 0.90), int(w * 0.20):int(w * 0.80)]
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv, (18, 160, 160), (38, 255, 255))
    return cv2.countNonZero(yellow) > 400

def _elixir_purple_count(screen):
    h, w = screen.shape[:2]
    region = screen[int(h * 0.86):int(h * 0.93), int(w * 0.05):int(w * 0.55)]
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    purple = cv2.inRange(hsv, (130, 60, 60), (160, 255, 255))
    return cv2.countNonZero(purple)

def is_in_battle(screen):
    return _elixir_purple_count(screen) > 80

def find_ok_button(screen):
    """
    Locate the OK/continue button on the result screen.
    Layer 1: template matching (most reliable).
    Layer 2: HSV blue blob with wide fallback.
    Layer 3: OCR scan for button text.
    """
    # Template matching
    for name in ("ok_button", "play_again", "chest_ok", "continue"):
        m = _match_template(screen, name)
        if m:
            return m[0], m[1]

    # HSV color detection — tight range then wider fallback
    h, w = screen.shape[:2]
    y0, y1 = int(h * 0.55), int(h * 0.85)
    x0, x1 = int(w * 0.20), int(w * 0.80)
    region = screen[y0:y1, x0:x1]
    hsv    = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

    blue = cv2.inRange(hsv, (100, 180, 180), (125, 255, 255))
    if cv2.countNonZero(blue) < 150:
        blue = cv2.inRange(hsv, (95, 100, 120), (130, 255, 255))

    if cv2.countNonZero(blue) >= 80:
        M = cv2.moments(blue)
        if M["m00"] != 0:
            return (int(M["m10"] / M["m00"]) + x0,
                    int(M["m01"] / M["m00"]) + y0)

    # OCR scan for button text in the lower half
    if _ocr_engine:
        text = _ocr_text(screen[y0:y1, x0:x1])
        if any(kw in text for kw in ("ok", "play again", "continue", "collect")):
            return int(w * 0.50), int((y0 + y1) / 2)

    return None

def is_battle_ended(screen):
    return find_ok_button(screen) is not None

def did_win(screen):
    """
    Determine win/loss from the result screen.
    Layer 1: template matching for victory/defeat banners.
    Layer 2: OCR for "Victory" / "Defeat" text.
    Layer 3: banner color (blue = local player = winner at bottom).
    """
    # Template matching
    if _match_template(screen, "victory"):
        if DEBUG: print("[did_win] template → WIN")
        return True
    if _match_template(screen, "defeat"):
        if DEBUG: print("[did_win] template → LOSS")
        return False

    # OCR
    if _ocr_engine:
        h, w = screen.shape[:2]
        text = _ocr_text(screen[int(h * 0.20):int(h * 0.55), :])
        if "victory" in text:
            if DEBUG: print(f"[did_win] ocr ({_ocr_engine}) → WIN")
            return True
        if "defeat" in text:
            if DEBUG: print(f"[did_win] ocr ({_ocr_engine}) → LOSS")
            return False

    # Banner color fallback: winner is at bottom (blue banner), loser at top
    h, w = screen.shape[:2]
    bottom = screen[int(h*0.60):int(h*0.68), int(w*0.10):int(w*0.90)]
    top    = screen[int(h*0.30):int(h*0.38), int(w*0.10):int(w*0.90)]

    def blue_px(r):
        hsv = cv2.cvtColor(r, cv2.COLOR_BGR2HSV)
        return cv2.countNonZero(cv2.inRange(hsv, (100, 100, 80), (130, 255, 255)))

    b, t = blue_px(bottom), blue_px(top)
    if DEBUG:
        print(f"[did_win] color → bottom_blue={b} top_blue={t} → {'WIN' if b > t else 'LOSS'}")
    return b > t

def get_elixir(screen):
    return min(10, int(_elixir_purple_count(screen) / 15))

def is_loading(screen):
    h, w = screen.shape[:2]
    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    dark = cv2.countNonZero(cv2.threshold(gray, 20, 255, cv2.THRESH_BINARY_INV)[1])
    return dark > (w * h * 0.7)

def is_matchmaking(screen):
    h, w = screen.shape[:2]
    region = screen[int(h * 0.78):int(h * 0.90), int(w * 0.25):int(w * 0.75)]
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    r1 = cv2.inRange(hsv, (0,   150, 150), (10,  255, 255))
    r2 = cv2.inRange(hsv, (170, 150, 150), (180, 255, 255))
    return cv2.countNonZero(r1) + cv2.countNonZero(r2) > 200

# ─── SCREEN STATE + VISION PIPELINE ─────────────────────────────────────────

class ScreenState:
    """
    Wraps a screen state string with a detection confidence and the method
    that produced it ("color", "template", "ocr").

    String class constants allow comparisons like:
        state == ScreenState.BATTLE
    against both other ScreenState instances and plain strings.
    """
    BATTLE      = "battle"
    RESULT      = "result"
    HOME        = "home"
    MATCHMAKING = "matchmaking"
    LOADING     = "loading"
    UNKNOWN     = "unknown"

    MIN_CONFIDENCE = 0.90   # threshold for "confident enough to act"

    def __init__(self, state: str, confidence: float, method: str = "color"):
        self.state      = state
        self.confidence = confidence
        self.method     = method

    def __eq__(self, other):
        if isinstance(other, str):
            return self.state == other
        if isinstance(other, ScreenState):
            return self.state == other.state
        return NotImplemented

    def __str__(self):
        return self.state

    def __repr__(self):
        return (f"ScreenState({self.state!r}, "
                f"conf={self.confidence:.2f}, via={self.method})")

    @property
    def is_confident(self):
        return self.confidence >= self.MIN_CONFIDENCE

# ─── TEMPLATE MATCHING LAYER ──────────────────────────────────────────────────
# Drop PNG files into src/templates/ and they will be used automatically.
# Suggested filenames: ok_button.png, play_again.png, battle_button.png,
#   victory.png, defeat.png, chest_ok.png, cancel.png
_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
_template_cache: dict = {}

def _load_template(name: str):
    if name not in _template_cache:
        path = os.path.join(_TEMPLATES_DIR, f"{name}.png")
        _template_cache[name] = cv2.imread(path) if os.path.exists(path) else None
    return _template_cache[name]

def _match_template(screen, name: str, threshold: float = 0.80):
    """
    Match a named template against screen.
    Returns (cx, cy, confidence) if found above threshold, else None.
    """
    tmpl = _load_template(name)
    if tmpl is None:
        return None
    th, tw = tmpl.shape[:2]
    sh, sw = screen.shape[:2]
    if th > sh or tw > sw:
        return None
    result = cv2.matchTemplate(screen, tmpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val >= threshold:
        return max_loc[0] + tw // 2, max_loc[1] + th // 2, float(max_val)
    return None

# ─── OCR LAYER (optional — install pytesseract to enable) ────────────────────
_ocr_engine = None
try:
    import pytesseract as _pyt
    _ocr_engine = "pytesseract"
except ImportError:
    pass

if _ocr_engine is None:
    try:
        import easyocr as _eocr
        _eocr_reader = _eocr.Reader(["en"], gpu=False, verbose=False)
        _ocr_engine  = "easyocr"
    except ImportError:
        pass

_OCR_RESULT_KW  = {"victory", "defeat", "ok", "play again", "continue"}
_OCR_HOME_KW    = {"battle", "clan", "shop", "events"}
_OCR_MM_KW      = {"cancel", "searching", "found"}

def _ocr_text(region) -> str:
    """Return lowercase OCR text for a BGR image region, or '' if unavailable."""
    if _ocr_engine == "pytesseract":
        try:
            return _pyt.image_to_string(region).lower()
        except Exception:
            return ""
    if _ocr_engine == "easyocr":
        try:
            return " ".join(_eocr_reader.readtext(region, detail=0)).lower()
        except Exception:
            return ""
    return ""

# ─── CENTRAL DETECTOR ────────────────────────────────────────────────────────

def detect_screen(screen) -> ScreenState:
    """
    3-layer pipeline: color → template → OCR.
    Returns a ScreenState with confidence and detection method.
    The bot acts on any state; confidence is logged for debugging.

    Layer order:
      1. Color (fast, existing HSV checks)
      2. Template matching (if PNG files exist in src/templates/)
      3. OCR (if pytesseract or easyocr is installed)
    """
    # ── Layer 1: color-based fast checks ──────────────────────────────────
    if is_in_battle(screen):
        return ScreenState(ScreenState.BATTLE, 0.85, "color")

    if is_matchmaking(screen):
        return ScreenState(ScreenState.MATCHMAKING, 0.80, "color")

    if is_loading(screen):
        return ScreenState(ScreenState.LOADING, 0.85, "color")

    # ── Layer 2: template matching ─────────────────────────────────────────
    for tmpl_name in ("ok_button", "play_again", "chest_ok", "continue"):
        m = _match_template(screen, tmpl_name)
        if m:
            return ScreenState(ScreenState.RESULT, m[2], "template")

    m = _match_template(screen, "victory")
    if m:
        return ScreenState(ScreenState.RESULT, m[2], "template")

    m = _match_template(screen, "battle_button")
    if m:
        return ScreenState(ScreenState.HOME, m[2], "template")

    # ── Color fallbacks (less reliable, checked after templates) ───────────
    if is_battle_ended(screen):
        return ScreenState(ScreenState.RESULT, 0.75, "color")

    if is_on_home_screen(screen):
        return ScreenState(ScreenState.HOME, 0.80, "color")

    # ── Layer 3: OCR ──────────────────────────────────────────────────────
    if _ocr_engine:
        h, w = screen.shape[:2]
        text = _ocr_text(screen[int(h * 0.35):int(h * 0.90), :])
        if any(kw in text for kw in _OCR_RESULT_KW):
            return ScreenState(ScreenState.RESULT, 0.92, "ocr")
        if any(kw in text for kw in _OCR_HOME_KW):
            return ScreenState(ScreenState.HOME, 0.88, "ocr")
        if any(kw in text for kw in _OCR_MM_KW):
            return ScreenState(ScreenState.MATCHMAKING, 0.88, "ocr")

    return ScreenState(ScreenState.UNKNOWN, 1.0, "color")

# ─── TOWER HP DETECTION ──────────────────────────────────────────────────────

_TOWER_REGIONS = {
    "our_king":    (0.82, 0.86, 0.35, 0.65, "green"),
    "our_left":    (0.74, 0.78, 0.04, 0.22, "green"),
    "our_right":   (0.74, 0.78, 0.78, 0.96, "green"),
    "their_king":  (0.12, 0.16, 0.35, 0.65, "red"),
    "their_left":  (0.20, 0.24, 0.04, 0.22, "red"),
    "their_right": (0.20, 0.24, 0.78, 0.96, "red"),
}

def _bar_fill_pct(region, colour):
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    if colour == "green":
        mask = cv2.inRange(hsv, (40, 80, 80), (85, 255, 255))
    else:
        m1 = cv2.inRange(hsv, (0,   120, 120), (10,  255, 255))
        m2 = cv2.inRange(hsv, (165, 120, 120), (180, 255, 255))
        mask = cv2.bitwise_or(m1, m2)
    total = region.shape[0] * region.shape[1]
    return round(cv2.countNonZero(mask) / total * 100, 1) if total else 100

def sample_tower_hp(screen):
    h, w = screen.shape[:2]
    return {
        name: _bar_fill_pct(
            screen[int(h*y0):int(h*y1), int(w*x0):int(w*x1)], colour
        )
        for name, (y0, y1, x0, x1, colour) in _TOWER_REGIONS.items()
    }

def classify_lane(x_norm):
    if x_norm < 0.40: return "left"
    if x_norm > 0.60: return "right"
    return "center"

# ─── CARD TAP POSITIONS ──────────────────────────────────────────────────────

def get_card_tap_positions(w, h):
    y = int(h * 0.885)
    return {
        0: (int(w * 0.18), y),
        1: (int(w * 0.36), y),
        2: (int(w * 0.54), y),
        3: (int(w * 0.72), y),
    }

# ─── REWARD ENGINE (#10 — data collection, ML training hooks) ────────────────
class RewardEngine:
    """
    Records per-placement outcomes for future ML training.
    Computes tower-damage delta, elixir spent, and phase context.
    Future: train a reward model to predict EV of each action (#11).
    """
    def __init__(self):
        self.events = []

    def record(self, placement, hp_before, hp_after, elixir_spent):
        our_dmg   = (hp_before.get("their_left",  100) - hp_after.get("their_left",  100) +
                     hp_before.get("their_right", 100) - hp_after.get("their_right", 100) +
                     hp_before.get("their_king",  100) - hp_after.get("their_king",  100))
        their_dmg = (hp_before.get("our_left",  100) - hp_after.get("our_left",  100) +
                     hp_before.get("our_right", 100) - hp_after.get("our_right", 100) +
                     hp_before.get("our_king",  100) - hp_after.get("our_king",  100))
        # Exchange value: damage delta per elixir spent
        # Positive = we profited from this card play
        exchange = round((our_dmg - their_dmg) / max(1, elixir_spent), 3)
        self.events.append({
            **placement,
            "our_tower_dmg":   round(our_dmg,   2),
            "their_tower_dmg": round(their_dmg, 2),
            "elixir_spent":    elixir_spent,
            "exchange_ratio":  exchange,
            "ev":              None,   # populated by future reward model
        })

# ─── REPLAY LOGGER ───────────────────────────────────────────────────────────

class ReplayLogger:
    HP_SAMPLE_INTERVAL = 10

    def __init__(self, screen_w, screen_h, deck):
        ts = datetime.now(timezone.utc)
        self.battle_id  = f"bot_{ts.strftime('%Y%m%d_%H%M%S')}_{random.randint(1000,9999)}"
        self.started_at = ts.isoformat()
        self.screen_w   = screen_w
        self.screen_h   = screen_h
        self.our_deck   = list(deck)          # all 8 cards in cycle order
        self.placements        = []
        self.tower_hp_timeline = []
        self.wait_events       = []
        self._start_time      = time.time()
        self._last_hp_sample  = -self.HP_SAMPLE_INTERVAL

    def elapsed_ms(self):
        return int((time.time() - self._start_time) * 1000)

    def maybe_sample_hp(self, screen=None, towers=None):
        elapsed = time.time() - self._start_time
        if elapsed - self._last_hp_sample < self.HP_SAMPLE_INTERVAL:
            return None
        if towers is None:
            if screen is None:
                return None
            towers = sample_tower_hp(screen)
        self.tower_hp_timeline.append({"game_time_ms": int(elapsed * 1000), **towers})
        self._last_hp_sample = elapsed
        return towers

    def log_placement(self, card_slot, card_name, tx, ty,
                      elixir, phase, battle_phase,
                      tile_name="", prev_card="", opponent_cards_seen=None):
        x_norm = round(tx / self.screen_w, 3)
        y_norm = round(ty / self.screen_h, 3)
        entry = {
            "card_slot":           card_slot,
            "card_name":           card_name,
            "card_type":           card_type(card_name),
            "game_time_ms":        self.elapsed_ms(),
            "x_norm":              x_norm,
            "y_norm":              y_norm,
            "lane":                classify_lane(x_norm),
            "tile_name":           tile_name,
            "side":                "ours",
            "elixir":              elixir,
            "phase":               phase,
            "battle_phase":        battle_phase,
            "prev_card":           prev_card,
            "opponent_cards_seen": opponent_cards_seen or [],
        }
        self.placements.append(entry)
        return entry

    def log_wait(self, reason, duration_ms, phase=""):
        """Record a hold decision — used to learn human waiting behaviour."""
        self.wait_events.append({
            "game_time_ms": self.elapsed_ms(),
            "reason":       reason,
            "duration_ms":  duration_ms,
            "phase":        phase,
        })

    def to_dict(self, result="unknown", reward_events=None, opponent_archetype="unknown"):
        return {
            "battle_id":           self.battle_id,
            "started_at":          self.started_at,
            "result":              result,
            "duration_ms":         self.elapsed_ms(),
            "source":              "bot_mumu",
            "our_deck":            self.our_deck,
            "opponent_archetype":  opponent_archetype,
            "placements":          self.placements,
            "tower_hp_timeline":   self.tower_hp_timeline,
            "wait_events":         self.wait_events,
            "reward_events":       reward_events or [],
        }

    def save_local(self, result="unknown", reward_events=None, opponent_archetype="unknown"):
        os.makedirs(REPLAY_DIR, exist_ok=True)
        path = os.path.join(REPLAY_DIR, f"{self.battle_id}.json")
        with open(path, "w") as f:
            json.dump(self.to_dict(result, reward_events, opponent_archetype), f, indent=2)
        print(f"Replay saved → {path}")
        return path

    def send_to_worker(self, result="unknown", reward_events=None, opponent_archetype="unknown"):
        try:
            res = requests.post(
                f"{WORKER_URL}/bot/battle",
                json=self.to_dict(result, reward_events, opponent_archetype),
                timeout=10,
            )
            return res.ok
        except Exception as e:
            print(f"Worker send error: {e}")
            return False

# ─── VISUAL SNAPSHOT ─────────────────────────────────────────────────────────

class VisualSnapshot:
    """
    Immutable record of everything VisionEngine sees in a single frame.
    Produced once per tick; consumed by GameState and DecisionEngine.
    """
    __slots__ = ("screen_state", "towers", "troops", "elixir", "ok_button")

    def __init__(self, screen_state, towers, troops, elixir, ok_button):
        self.screen_state = screen_state   # ScreenState instance
        self.towers       = towers         # dict from sample_tower_hp, or {}
        self.troops       = troops         # list of {x_norm, y_norm} blobs
        self.elixir       = elixir         # int 0-10
        self.ok_button    = ok_button      # (x, y) or None

# ─── VISION ENGINE ────────────────────────────────────────────────────────────

class VisionEngine:
    """
    Single entry point for all visual detection.
    Screenshot → VisualSnapshot in one call.
    Owns the TroopDetector so frame-diff state is preserved across ticks.
    """
    def __init__(self):
        self._troop_det = TroopDetector()

    def analyze(self, screen) -> VisualSnapshot:
        ss = detect_screen(screen)
        ib = (ss == ScreenState.BATTLE)
        return VisualSnapshot(
            screen_state = ss,
            towers    = sample_tower_hp(screen) if ib else {},
            troops    = self._troop_det.detect(screen) if ib else [],
            elixir    = get_elixir(screen) if ib else 0,
            ok_button = find_ok_button(screen) if ss == ScreenState.RESULT else None,
        )

# ─── UNIFIED GAME STATE ───────────────────────────────────────────────────────

class GameState:
    """
    Accumulated battle context updated every tick.
    VisionEngine fills `.visual`; everything else evolves from that.
    """
    def __init__(self, deck, screen_w, screen_h):
        self.rotation      = CardRotation(deck)
        self.phase_machine = BattleStateMachine()
        self.lane_pressure = LanePressureTracker()
        self.archetype     = ArchetypeDetector()
        self.opp_cycle     = OpponentCycleTracker()
        self.replay        = ReplayLogger(screen_w, screen_h, deck)

        self.visual        = None     # latest VisualSnapshot
        self.game_time     = 0.0
        self.prev_card     = ""
        self.cards_played  = 0
        self._start_time   = time.time()

    def tick(self, visual: VisualSnapshot):
        self.visual    = visual
        self.game_time = time.time() - self._start_time
        if visual.towers:
            self.lane_pressure.update(visual.towers)
            self.replay.maybe_sample_hp(towers=visual.towers)
        self.phase_machine.update(self.game_time, self.lane_pressure)

    @property
    def phase(self):
        return self.phase_machine.phase

    @property
    def is_double(self):
        return self.phase_machine.is_double

    @property
    def hand(self):
        return self.rotation.hand

# ─── OPENING BOOK ─────────────────────────────────────────────────────────────

class OpeningBook:
    """Scripted tile pool for the first 15 s of a battle."""
    _BOOK = {
        "cycle":         ["bridge_left", "bridge_right"],
        "win_condition": ["bridge_left", "bridge_right"],
        "support":       ["support_left", "support_right"],
        "mini_tank":     ["support_left", "support_right"],
        "tank":          ["support_left", "support_right"],
    }

    def suggest_tile(self, card_name, game_time, hot_lane):
        if game_time > 15:
            return None
        pool = self._BOOK.get(card_type(card_name))
        if not pool:
            return None
        if hot_lane == "left":
            pool = [t for t in pool if "left" in t] or pool
        elif hot_lane == "right":
            pool = [t for t in pool if "right" in t] or pool
        return random.choice(pool)

# ─── BOARD EVALUATOR ─────────────────────────────────────────────────────────

class BoardEvaluator:
    """Summarises board state from a GameState for decision-making."""
    def score(self, gs: GameState) -> dict:
        lp = gs.lane_pressure
        tw = gs.visual.towers if gs.visual else {}
        return {
            "pressure_left":  lp.left,
            "pressure_right": lp.right,
            "hot_lane":       lp.hot_lane,
            "under_attack":   lp.under_attack,
            "our_hp_min":     min(tw.get("our_left", 100), tw.get("our_right", 100)),
            "their_hp_min":   min(tw.get("their_left", 100), tw.get("their_right", 100)),
        }

# ─── SPELL EVALUATOR ─────────────────────────────────────────────────────────

class SpellEvaluator:
    """Gates spell casts on troop density using spell_target_value."""
    def can_cast(self, card_name, tx, ty, w, h, troops) -> bool:
        if not troops:
            return True
        value   = spell_target_value(card_name, tx / w, ty / h, troops)
        min_hit = 1 if card_type(card_name) == "spell_big" else 3
        return value >= min_hit

# ─── ACTIONS ─────────────────────────────────────────────────────────────────

class Action:
    def execute(self):
        raise NotImplementedError

class TapAction(Action):
    def __init__(self, x, y):
        self.x, self.y = x, y
    def execute(self):
        tap(self.x, self.y)

class DragAction(Action):
    def __init__(self, x1, y1, x2, y2, duration_ms=150):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.duration_ms = duration_ms
    def execute(self):
        drag(self.x1, self.y1, self.x2, self.y2, self.duration_ms)

class WaitAction(Action):
    def __init__(self, duration=0.1):
        self.duration = duration
    def execute(self):
        time.sleep(self.duration)

class PlayCardAction(Action):
    def __init__(self, slot, card_name, from_xy, to_xy, tile_name=""):
        self.slot      = slot
        self.card_name = card_name
        self.from_x, self.from_y = from_xy
        self.to_x,   self.to_y   = to_xy
        self.tile_name = tile_name
    def execute(self):
        drag(self.from_x, self.from_y, self.to_x, self.to_y)

# ─── DECISION ENGINE ─────────────────────────────────────────────────────────

class DecisionEngine:
    """
    Consumes a GameState, returns an Action.
    Owns all sub-evaluators and the deferred-reward tracker.
    """
    def __init__(self):
        self.opening_book    = OpeningBook()
        self.spell_evaluator = SpellEvaluator()
        self.board_evaluator = BoardEvaluator()
        self.enemy_elixir    = EnemyElixirTracker()
        self.reward_scorer   = RewardEngine()
        self._last_play_t    = 0.0
        self._play_cooldown  = human_play_interval()
        self._wait_start     = None
        self.pending_reward  = None

    def decide(self, gs: GameState, w: int, h: int, card_positions: dict) -> Action:
        visual = gs.visual
        self.enemy_elixir.update(is_double=gs.is_double)

        cooldown_ok = time.time() - self._last_play_t >= self._play_cooldown
        elixir_ok   = visual.elixir >= 4 or DEBUG_FORCE_PLAY
        skip_rand   = (not DEBUG_FORCE_PLAY) and random.random() < 0.20

        if not (cooldown_ok and elixir_ok and not skip_rand):
            if self._wait_start is None:
                self._wait_start = time.time()
            return WaitAction(random.uniform(0.05, 0.15))

        # Resolve deferred reward from the previous card play
        if self.pending_reward is not None and visual.towers:
            self.reward_scorer.record(
                self.pending_reward["entry"],
                self.pending_reward["hp_before"],
                visual.towers,
                self.pending_reward["elixir"],
            )
            self.pending_reward = None

        # Log the wait that just ended
        if self._wait_start is not None:
            gs.replay.log_wait("cooldown",
                               int((time.time() - self._wait_start) * 1000),
                               gs.phase)
            self._wait_start = None

        phase  = gs.phase
        troops = visual.troops
        board  = self.board_evaluator.score(gs)

        candidates = []
        for s in range(4):
            cname = gs.rotation.card_at(s)
            pos   = get_play_position(cname, phase, gs.lane_pressure,
                                      gs.game_time, w, h, troops)
            if pos is None:
                continue
            tx, ty, tile_name = pos
            if card_type(cname) in _SPELL_LIKE:
                if not self.spell_evaluator.can_cast(cname, tx, ty, w, h, troops):
                    continue
            sc  = COMBO_DB.score_follow_up(gs.prev_card, cname, phase)
            ctp = card_type(cname)
            if phase == PHASE_DEFENDING and ctp in ("mini_tank", "building", "spell_small"):
                sc += 0.3
            elif phase == PHASE_COUNTERPUSH and ctp in ("win_condition", "tank", "support"):
                sc += 0.3
            elif phase in (PHASE_DOUBLE, PHASE_OVERTIME) and ctp in ("win_condition", "spell_big"):
                sc += 0.2
            candidates.append((sc, s, cname, (tx, ty, tile_name)))

        if not candidates:
            gs.replay.log_wait("all_held", 0, phase)
            return WaitAction(random.uniform(0.05, 0.15))

        _, slot, card_name, (tx, ty, tile_name) = max(candidates, key=lambda x: x[0])
        cx, cy = card_positions[slot]
        return PlayCardAction(slot, card_name, (cx, cy), (tx, ty), tile_name)

    def apply(self, action: Action, gs: GameState, w: int, h: int) -> None:
        """Execute the action and update GameState. Call after decide()."""
        if isinstance(action, PlayCardAction):
            hp_before = dict(gs.visual.towers) if gs.visual.towers else {}
            action.execute()

            phase_str = "early" if gs.game_time < 90 else "double"
            entry = gs.replay.log_placement(
                action.slot, action.card_name, action.to_x, action.to_y,
                gs.visual.elixir, phase_str, gs.phase,
                tile_name=action.tile_name,
                prev_card=gs.prev_card,
                opponent_cards_seen=gs.opp_cycle.cards_seen,
            )
            self.pending_reward = {
                "entry":    entry,
                "hp_before": hp_before,
                "elixir":   gs.visual.elixir,
            }
            gs.rotation.play(action.slot)
            gs.prev_card     = action.card_name
            gs.cards_played += 1
            self._last_play_t   = time.time()
            learned_wait        = WAIT_DB.sample_wait(gs.phase)
            self._play_cooldown = (learned_wait if learned_wait
                                   else human_play_interval(gs.phase))
        else:
            action.execute()

# ─── MAIN BOT ────────────────────────────────────────────────────────────────

class RoyaleBot:
    def __init__(self, on_status=None):
        self.running = False
        self.battles_played = 0
        self.wins = 0
        self.losses = 0
        self.on_status = on_status
        self.screen_w = None
        self.screen_h = None
        self._battle_confirm  = 0
        self._coords_saved    = False
        self._cached_deck     = None   # refreshed every 5 battles
        self._break_taken_at  = -1    # tracks which battle count last triggered a break
        self.anti_detect      = True   # pause every 10 battles; toggled by GUI

    def _get_deck(self):
        if self._cached_deck is None or self.battles_played % 5 == 0:
            self._cached_deck = fetch_deck()
            self.log(f"🃏 Deck: {self._cached_deck}")
        return self._cached_deck

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}")
        if self.on_status:
            self.on_status(msg)

    def find_and_tap_battle(self, screen):
        m = _match_template(screen, "battle_button")
        if m:
            bx, by = m[0], m[1]
            self.log(f"🎮 Battle button (template) at ({bx},{by}) conf={m[2]:.2f}")
        else:
            h, w = screen.shape[:2]
            bx, by = int(w * 0.40), int(h * 0.77)
            self.log(f"🎮 Battle button (hardcoded) at ({bx},{by})")
        tap(bx, by)
        time.sleep(2)

    def play_battle(self):
        deck   = self._get_deck()
        vision = VisionEngine()
        gs     = GameState(deck, self.screen_w, self.screen_h)
        engine = DecisionEngine()
        w, h   = self.screen_w, self.screen_h
        card_positions = get_card_tap_positions(w, h)
        result = "loss"

        self.log(f"⚔️ Battle #{self.battles_played + 1} | id={gs.replay.battle_id}")
        self.log(f"🃏 Card slots: {card_positions}")

        if DEBUG_SAVE_COORDS and not self._coords_saved:
            try:
                save_coord_overlay(screenshot(), card_positions)
                self._coords_saved = True
            except Exception as e:
                self.log(f"Coord overlay error: {e}")

        while time.time() - gs._start_time < 250:
            if not self.running:
                break
            try:
                screen = screenshot()
                visual = vision.analyze(screen)
                gs.tick(visual)

                # Battle end detection
                if gs.game_time > 20 and visual.screen_state == ScreenState.RESULT:
                    result = "win" if did_win(screen) else "loss"
                    self.log(f"{'🏆 WIN' if result == 'win' else '💀 LOSS'}!")
                    break

                if visual.screen_state != ScreenState.BATTLE:
                    time.sleep(0.05)
                    continue

                if DEBUG:
                    self.log(
                        f"💧 {visual.elixir}/10  t={int(gs.game_time)}s  "
                        f"phase={gs.phase}  arch={gs.archetype.archetype}  "
                        f"lane L={gs.lane_pressure.left:.0f} R={gs.lane_pressure.right:.0f}  "
                        f"enemy_ex≈{engine.enemy_elixir.estimate:.1f}  "
                        f"troops={len(visual.troops)}  hand={gs.hand}"
                    )

                # Vision Engine → GameState → Decision Engine → Action
                action = engine.decide(gs, w, h, card_positions)

                if isinstance(action, PlayCardAction):
                    self.log(
                        f"🃏 {action.card_name} [{card_type(action.card_name)}] "
                        f"tile={action.tile_name} "
                        f"({action.from_x},{action.from_y})→({action.to_x},{action.to_y}) "
                        f"lane={classify_lane(action.to_x / w)} "
                        f"elixir={visual.elixir} phase={gs.phase}"
                    )

                engine.apply(action, gs, w, h)

            except Exception as e:
                self.log(f"Battle error: {e}")
                time.sleep(1)

        # Resolve any dangling deferred reward
        if engine.pending_reward is not None:
            try:
                final_towers = sample_tower_hp(screenshot())
                engine.reward_scorer.record(
                    engine.pending_reward["entry"],
                    engine.pending_reward["hp_before"],
                    final_towers,
                    engine.pending_reward["elixir"],
                )
            except Exception:
                pass

        won  = result == "win"
        arch = gs.archetype.archetype

        for p in gs.replay.placements:
            PLACEMENT_DB.record(p["card_name"], p["battle_phase"], p["lane"],
                                p["x_norm"], p["y_norm"], won)
        PLACEMENT_DB.save()

        prev = ""
        for p in gs.replay.placements:
            if prev:
                COMBO_DB.record(prev, p["card_name"], p["battle_phase"], won)
            prev = p["card_name"]
        COMBO_DB.save()

        WAIT_DB.record_battle(gs.replay.wait_events)
        WAIT_DB.save()

        db_summary = PLACEMENT_DB.summary()
        if db_summary:
            self.log(f"📊 PlacementDB: {len(db_summary)} keys learned | arch={arch}")

        gs.replay.save_local(result, engine.reward_scorer.events, arch)
        ok = gs.replay.send_to_worker(result, engine.reward_scorer.events, arch)
        self.log(
            f"{'✅' if ok else '⚠️'} Replay synced "
            f"({len(gs.replay.placements)} placements, "
            f"{len(gs.replay.tower_hp_timeline)} HP snapshots, "
            f"{len(engine.reward_scorer.events)} reward events)"
        )

        if result == "win":
            self.wins += 1
        else:
            self.losses += 1
        self.battles_played += 1
        return result == "win"

    def run(self):
        self.running = True
        self.log("🤖 RoyaleBot started!")
        if DEBUG:
            self.log(f"🐛 DEBUG ON | FORCE_PLAY={DEBUG_FORCE_PLAY} | "
                     f"NO_JITTER={DEBUG_NO_JITTER}")

        subprocess.run([ADB, "connect", DEVICE], capture_output=True)
        time.sleep(1)

        first = screenshot()
        self.screen_h, self.screen_w = first.shape[:2]
        self.log(f"📐 Screen: {self.screen_w}x{self.screen_h}")

        vision = VisionEngine()   # shared across outer-loop ticks

        while self.running:
            try:
                screen = screenshot()
                visual = vision.analyze(screen)
                state  = visual.screen_state

                if state == ScreenState.BATTLE:
                    self._battle_confirm += 1
                    if self._battle_confirm >= BATTLE_DEBOUNCE:
                        self._battle_confirm = 0
                        self.play_battle()

                elif state == ScreenState.RESULT:
                    self._battle_confirm = 0
                    if visual.ok_button:
                        self.log(f"👆 Dismiss result at {visual.ok_button}")
                        tap(*visual.ok_button)
                        time.sleep(0.8)
                    else:
                        time.sleep(0.2)

                elif state == ScreenState.HOME:
                    self._battle_confirm = 0
                    self.log("🏠 Home — tapping Battle")
                    self.find_and_tap_battle(screen)
                    self.log("⏳ Waiting for battle...")
                    _mm_start = time.time()
                    while self.running and time.time() - _mm_start < 60:
                        scr = screenshot()
                        if is_in_battle(scr):
                            self.log("⚔️ Battle started!")
                            break
                        time.sleep(0.5 if is_matchmaking(scr) else 0.2)

                elif state == ScreenState.MATCHMAKING:
                    self._battle_confirm = 0
                    self.log("⏳ Matchmaking...")
                    time.sleep(0.5)

                elif state == ScreenState.LOADING:
                    self._battle_confirm = 0
                    time.sleep(0.3)

                else:
                    self._battle_confirm = 0
                    self.log("🔍 Unknown screen — debug screenshot saved")
                    save_screenshot(r"C:\debug_screen.png")
                    time.sleep(2)

                # Anti-detection break every 10 battles (guard against re-trigger)
                b = self.battles_played
                if (self.anti_detect and b > 0
                        and b % 10 == 0 and b != self._break_taken_at):
                    self._break_taken_at = b
                    brk = random.randint(120, 300)
                    self.log(f"☕ Anti-detection break: {brk}s")
                    time.sleep(brk)

                time.sleep(0.1)

            except Exception as e:
                self.log(f"Main loop error: {e}")
                time.sleep(2)

        self.log("⏹️ Bot stopped.")

    def stop(self):
        self.running = False

# ─── GUI ─────────────────────────────────────────────────────────────────────

try:
    import customtkinter as ctk

    class BotGUI:
        def __init__(self):
            self.bot    = None
            self.thread = None
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("dark-blue")
            self.root = ctk.CTk()
            self.root.title("👑 RoyaleBot AI")
            self.root.geometry("500x700")
            self.root.resizable(False, False)

            header = ctk.CTkFrame(self.root, fg_color="#0a0a1a", corner_radius=0)
            header.pack(fill="x")
            ctk.CTkLabel(header, text="👑 ROYALE BOT AI",
                font=("Arial", 24, "bold"), text_color="#ff6f00").pack(pady=10)
            ctk.CTkLabel(header,
                text="State machine · Lane pressure · Human timing · Replay logging",
                font=("Arial", 10), text_color="#333").pack(pady=2)

            sf = ctk.CTkFrame(self.root, fg_color="#111122")
            sf.pack(fill="x", padx=20, pady=10)
            self.dot = ctk.CTkLabel(sf, text="⬤", font=("Arial", 16), text_color="#ff5252")
            self.dot.pack(side="left", padx=10, pady=8)
            self.status_lbl = ctk.CTkLabel(sf, text="Stopped", font=("Arial", 13))
            self.status_lbl.pack(side="left", pady=8)

            stats = ctk.CTkFrame(self.root, fg_color="#0d0d1f")
            stats.pack(fill="x", padx=20, pady=5)
            stats.grid_columnconfigure((0,1,2), weight=1)

            self.battles_var = ctk.StringVar(value="0")
            self.wins_var    = ctk.StringVar(value="0")
            self.losses_var  = ctk.StringVar(value="0")

            for i, (lbl, var, col) in enumerate([
                ("BATTLES", self.battles_var, "#ff9a40"),
                ("WINS",    self.wins_var,    "#4caf50"),
                ("LOSSES",  self.losses_var,  "#f44336"),
            ]):
                f = ctk.CTkFrame(stats, fg_color="#111133")
                f.grid(row=0, column=i, padx=5, pady=10, sticky="ew")
                ctk.CTkLabel(f, textvariable=var, font=("Arial", 30, "bold"), text_color=col).pack(pady=5)
                ctk.CTkLabel(f, text=lbl, font=("Arial", 10), text_color="#555").pack(pady=2)

            self.wr_var = ctk.StringVar(value="Win Rate: --%")
            ctk.CTkLabel(self.root, textvariable=self.wr_var,
                font=("Arial", 13), text_color="#ffd700").pack(pady=3)

            # ── Player tag entry ──────────────────────────────────────────────
            tf = ctk.CTkFrame(self.root, fg_color="#0d0d1f")
            tf.pack(fill="x", padx=20, pady=(4, 0))
            tf.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(tf, text="Player Tag  #",
                font=("Arial", 12), text_color="#888", width=100).grid(
                row=0, column=0, padx=(10, 0), pady=8, sticky="w")
            self.tag_entry = ctk.CTkEntry(tf,
                font=("Arial", 13, "bold"),
                fg_color="#070718", border_color="#333",
                placeholder_text="ABC123",
                height=34)
            self.tag_entry.grid(row=0, column=1, padx=10, pady=8, sticky="ew")

            # ── Options row ───────────────────────────────────────────────────
            of = ctk.CTkFrame(self.root, fg_color="#0d0d1f")
            of.pack(fill="x", padx=20, pady=(0, 4))
            self.anti_detect_var = ctk.BooleanVar(value=True)
            self.anti_detect_cb  = ctk.CTkCheckBox(
                of,
                text="Anti-detection breaks (pause every 10 battles)",
                variable=self.anti_detect_var,
                font=("Arial", 11), text_color="#888",
                fg_color="#ff6f00", hover_color="#e65100",
                checkmark_color="#fff",
            )
            self.anti_detect_cb.pack(anchor="w", padx=12, pady=6)

            self._load_config()

            lf = ctk.CTkFrame(self.root, fg_color="#050510")
            lf.pack(fill="both", expand=True, padx=20, pady=5)
            ctk.CTkLabel(lf, text="BOT LOG", font=("Arial", 10, "bold"),
                         text_color="#333").pack(anchor="w", padx=8, pady=4)
            self.log_box = ctk.CTkTextbox(lf, font=("Courier", 11),
                fg_color="#030308", text_color="#4caf50", height=200)
            self.log_box.pack(fill="both", expand=True, padx=5, pady=5)

            bf = ctk.CTkFrame(self.root, fg_color="transparent")
            bf.pack(fill="x", padx=20, pady=8)
            bf.grid_columnconfigure((0,1), weight=1)

            self.start_btn = ctk.CTkButton(bf, text="▶  START BOT",
                font=("Arial", 14, "bold"), fg_color="#ff6f00", hover_color="#e65100",
                command=self.start, height=45)
            self.start_btn.grid(row=0, column=0, padx=5, sticky="ew")

            self.stop_btn = ctk.CTkButton(bf, text="⏹  STOP",
                font=("Arial", 14, "bold"), fg_color="#333", hover_color="#444",
                command=self.stop, height=45, state="disabled")
            self.stop_btn.grid(row=0, column=1, padx=5, sticky="ew")

            ctk.CTkButton(self.root, text="📸 Debug Screenshot",
                font=("Arial", 11), fg_color="#1a1a2e", hover_color="#222244",
                command=self.take_screenshot, height=32).pack(pady=5, padx=20, fill="x")

            ctk.CTkLabel(self.root, text=f"Replays → {REPLAY_DIR}",
                font=("Arial", 10), text_color="#1a1a1a").pack(pady=5)

        # ── Config persistence (saves player tag between sessions) ──────────
        _CONFIG_PATH = os.path.join(REPLAY_DIR, "gui_config.json")

        def _load_config(self):
            try:
                os.makedirs(REPLAY_DIR, exist_ok=True)
                with open(self._CONFIG_PATH) as f:
                    cfg = json.load(f)
                tag = cfg.get("player_tag", "")
                if tag:
                    self.tag_entry.insert(0, tag)
                self.anti_detect_var.set(cfg.get("anti_detect", True))
            except FileNotFoundError:
                pass
            except Exception as e:
                print(f"Config load error: {e}")

        def _save_config(self):
            try:
                os.makedirs(REPLAY_DIR, exist_ok=True)
                with open(self._CONFIG_PATH, "w") as f:
                    json.dump({
                        "player_tag":  self.tag_entry.get().strip(),
                        "anti_detect": self.anti_detect_var.get(),
                    }, f)
            except Exception as e:
                print(f"Config save error: {e}")

        def log(self, msg):
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_box.insert("end", f"[{ts}] {msg}\n")
            self.log_box.see("end")

        def update_stats(self):
            if self.bot:
                self.battles_var.set(str(self.bot.battles_played))
                self.wins_var.set(str(self.bot.wins))
                self.losses_var.set(str(self.bot.losses))
                total = self.bot.wins + self.bot.losses
                if total > 0:
                    self.wr_var.set(f"Win Rate: {round(self.bot.wins/total*100)}%")
            self.root.after(1000, self.update_stats)

        def take_screenshot(self):
            try:
                save_screenshot(r"C:\debug_screen.png")
                self.log("📸 Saved to C:\\debug_screen.png")
            except Exception as e:
                self.log(f"Screenshot error: {e}")

        def start(self):
            global PLAYER_TAG
            tag = self.tag_entry.get().strip().lstrip("#")
            if not tag:
                self.log("⚠️ Enter your player tag before starting!")
                return
            PLAYER_TAG = tag
            self._save_config()
            self.tag_entry.configure(state="disabled")
            self.anti_detect_cb.configure(state="disabled")

            self.bot = RoyaleBot(on_status=self.log)
            self.bot.anti_detect = self.anti_detect_var.get()
            self.thread = threading.Thread(target=self.bot.run, daemon=True)
            self.thread.start()
            self.dot.configure(text_color="#4caf50")
            self.status_lbl.configure(text="Running")
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
            ad = "ON" if self.bot.anti_detect else "OFF"
            self.log(f"🤖 Bot started! Tag: #{PLAYER_TAG}  Anti-detect: {ad}")

        def stop(self):
            if self.bot:
                self.bot.stop()
            self.dot.configure(text_color="#ff5252")
            self.status_lbl.configure(text="Stopped")
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self.tag_entry.configure(state="normal")
            self.anti_detect_cb.configure(state="normal")
            self.log("⏹️ Bot stopped.")

        def run(self):
            self.update_stats()
            self.root.mainloop()

    if __name__ == "__main__":
        app = BotGUI()
        app.run()

except ImportError:
    if __name__ == "__main__":
        print("No GUI — running headless")
        bot = RoyaleBot()
        bot.run()
