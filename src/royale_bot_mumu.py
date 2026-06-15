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
BATTLE_DEBOUNCE   = 2

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

def human_play_interval():
    """Return a play-cooldown drawn from a human-like timing distribution."""
    return random.choices(_TIMING_INTERVALS, weights=_TIMING_WEIGHTS, k=1)[0]

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

# ─── HAND SCORER (#5 + combo) ────────────────────────────────────────────────

def score_hand(hand, prev_card, phase, lane_p, game_time, troops=None):
    """
    Score each card slot (0-3) and return the best slot to play.
    Combines phase-fit heuristic + learned combo win rates.
    """
    scores = {}
    for slot, card in enumerate(hand):
        ctype  = card_type(card)
        score  = 0.0

        # Phase fit
        if phase == PHASE_DEFENDING:
            if ctype in ("mini_tank", "building", "spell_small"):
                score += 3
        elif phase == PHASE_COUNTERPUSH:
            if ctype in ("win_condition", "tank", "support"):
                score += 3
        elif phase in (PHASE_DOUBLE, PHASE_OVERTIME):
            if ctype in ("win_condition", "spell_big"):
                score += 2

        # Archetype fit: prefer win_condition when rushing is advised
        if lane_p.hot_lane is None and ctype == "win_condition":
            score += 1

        # Combo bonus
        score += COMBO_DB.score_follow_up(prev_card, card, phase) * 2

        # Spell penalty when there are no targets early
        if ctype in _SPELL_LIKE and game_time < 30:
            score -= 4
        elif ctype in _SPELL_LIKE and troops is not None and len(troops) < 2:
            score -= 2

        scores[slot] = score

    return max(scores, key=scores.get)

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
    h, w = screen.shape[:2]
    y0, y1 = int(h * 0.65), int(h * 0.82)
    x0, x1 = int(w * 0.25), int(w * 0.75)
    region = screen[y0:y1, x0:x1]
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    blue = cv2.inRange(hsv, (100, 180, 180), (125, 255, 255))
    if cv2.countNonZero(blue) < 150:
        return None
    M = cv2.moments(blue)
    if M["m00"] == 0:
        return None
    return (int(M["m10"] / M["m00"]) + x0,
            int(M["m01"] / M["m00"]) + y0)

def is_battle_ended(screen):
    return find_ok_button(screen) is not None

def did_win(screen):
    """
    CR places WINNER at bottom (blue banner), LOSER at top (red/pink banner).
    Local player always has blue; opponent has red/pink.
    TODO: replace with OCR of player name once pytesseract is available.
    """
    h, w = screen.shape[:2]
    bottom = screen[int(h*0.60):int(h*0.68), int(w*0.10):int(w*0.90)]
    top    = screen[int(h*0.30):int(h*0.38), int(w*0.10):int(w*0.90)]

    def blue_px(r):
        hsv = cv2.cvtColor(r, cv2.COLOR_BGR2HSV)
        return cv2.countNonZero(cv2.inRange(hsv, (100, 100, 80), (130, 255, 255)))

    b, t = blue_px(bottom), blue_px(top)
    if DEBUG:
        print(f"[did_win] bottom_blue={b} top_blue={t} → {'WIN' if b > t else 'LOSS'}")
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

    def maybe_sample_hp(self, screen):
        elapsed = time.time() - self._start_time
        if elapsed - self._last_hp_sample < self.HP_SAMPLE_INTERVAL:
            return None
        hp = sample_tower_hp(screen)
        self.tower_hp_timeline.append({"game_time_ms": int(elapsed * 1000), **hp})
        self._last_hp_sample = elapsed
        return hp

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
        self._battle_confirm = 0
        self._coords_saved   = False

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}")
        if self.on_status:
            self.on_status(msg)

    def find_and_tap_battle(self, screen):
        h, w = screen.shape[:2]
        bx, by = int(w * 0.40), int(h * 0.77)
        self.log(f"🎮 Tapping battle button at ({bx}, {by}) on {w}x{h}...")
        tap(bx, by)
        time.sleep(2)

    def dismiss_result(self):
        w, h = self.screen_w, self.screen_h
        fallback_x = int(w * 0.50)
        fallback_y = int(h * 0.73)

        time.sleep(2)
        for i in range(6):
            try:
                scr = screenshot()
                btn = find_ok_button(scr)
                if btn:
                    tap(btn[0], btn[1])
                    self.log(f"👆 Dismiss {i+1}/6 → button at {btn}")
                else:
                    tap(fallback_x, fallback_y)
                    self.log(f"👆 Dismiss {i+1}/6 → fallback ({fallback_x},{fallback_y})")
            except Exception as e:
                tap(fallback_x, fallback_y)
                self.log(f"👆 Dismiss {i+1}/6 → err ({e})")
            time.sleep(1.2)

    def play_battle(self):
        deck        = fetch_deck()
        replay      = ReplayLogger(self.screen_w, self.screen_h, deck)
        rotation    = CardRotation(deck)
        state       = BattleStateMachine()
        lane_p      = LanePressureTracker()
        enemy_ex    = EnemyElixirTracker()
        reward      = RewardEngine()
        troop_det   = TroopDetector()
        archetype   = ArchetypeDetector()
        opp_cycle   = OpponentCycleTracker()

        self.log(f"⚔️ Battle #{self.battles_played + 1} | id={replay.battle_id}")

        w, h = self.screen_w, self.screen_h
        card_positions = get_card_tap_positions(w, h)
        self.log(f"🃏 Card slots: {card_positions}")

        if DEBUG_SAVE_COORDS and not self._coords_saved:
            try:
                save_coord_overlay(screenshot(), card_positions)
                self._coords_saved = True
            except Exception as e:
                self.log(f"Coord overlay error: {e}")

        result       = "loss"
        battle_start = time.time()
        last_play_t  = 0
        cards_played = 0
        play_cooldown = human_play_interval()
        prev_hp      = {}
        prev_card    = ""       # last card played (for sequence logging)
        _wait_start  = None     # tracks when a wait period began

        while time.time() - battle_start < 250:
            if not self.running:
                break
            try:
                screen    = screenshot()
                game_time = time.time() - battle_start

                if game_time > 20 and is_battle_ended(screen):
                    result = "win" if did_win(screen) else "loss"
                    self.log(f"{'🏆 WIN' if result == 'win' else '💀 LOSS'}!")
                    break

                if not is_in_battle(screen):
                    time.sleep(1)
                    continue

                # HP sampling + systems update
                hp = replay.maybe_sample_hp(screen) or (
                    replay.tower_hp_timeline[-1] if replay.tower_hp_timeline else {})
                lane_p.update(hp)
                enemy_ex.update(is_double=state.is_double)
                state.update(game_time, lane_p)

                troops = troop_det.detect(screen)
                elixir = get_elixir(screen)

                if DEBUG:
                    self.log(
                        f"💧 {elixir}/10  t={int(game_time)}s  "
                        f"phase={state.phase}  arch={archetype.archetype}  "
                        f"lane L={lane_p.left:.0f} R={lane_p.right:.0f}  "
                        f"enemy_ex≈{enemy_ex.estimate:.1f}  "
                        f"troops={len(troops)}  hand={rotation.hand}"
                    )

                # Decide whether to play
                cooldown_ok = time.time() - last_play_t >= play_cooldown
                elixir_ok   = elixir >= 4 or DEBUG_FORCE_PLAY
                skip_rand   = (not DEBUG_FORCE_PLAY) and random.random() < 0.20

                if cooldown_ok and elixir_ok and not skip_rand:
                    # Flush any wait period that just ended
                    if _wait_start is not None:
                        replay.log_wait("cooldown",
                                        int((time.time() - _wait_start) * 1000),
                                        state.phase)
                        _wait_start = None

                    # Pick best slot from hand (combo + phase scoring)
                    slot      = score_hand(rotation.hand, prev_card, state.phase,
                                           lane_p, game_time, troops)
                    card_name = rotation.card_at(slot)
                    ctype     = card_type(card_name)
                    phase_str = "early" if game_time < 90 else "double"

                    pos = get_play_position(card_name, state.phase, lane_p,
                                            game_time, w, h, troops)

                    if pos is None:
                        self.log(f"⏭️ Hold {card_name} ({ctype}): no valid target")
                        replay.log_wait("held_spell", 0, state.phase)
                    else:
                        tx, ty, tile_name = pos
                        cx, cy = card_positions[slot]

                        hp_before = dict(hp)
                        drag(cx, cy, tx, ty, duration_ms=150)
                        rotation.play(slot)

                        x_n   = round(tx / w, 3)
                        entry = replay.log_placement(
                            slot, card_name, tx, ty,
                            elixir, phase_str, state.phase,
                            tile_name=tile_name,
                            prev_card=prev_card,
                        )

                        # Collect reward data after a short settle window
                        time.sleep(0.5)
                        scr2 = screenshot()
                        hp_after = sample_tower_hp(scr2)
                        reward.record(entry, hp_before, hp_after, elixir)

                        prev_card     = card_name
                        last_play_t   = time.time()
                        learned_wait  = WAIT_DB.sample_wait(state.phase)
                        play_cooldown = learned_wait if learned_wait else human_play_interval()
                        cards_played += 1

                        self.log(
                            f"🃏 {card_name} [{ctype}] tile={tile_name} "
                            f"({cx},{cy})→({tx},{ty}) "
                            f"lane={classify_lane(x_n)} "
                            f"elixir={elixir} phase={state.phase}"
                        )
                else:
                    if _wait_start is None:
                        _wait_start = time.time()

                time.sleep(random.uniform(0.3, 0.7))

            except Exception as e:
                self.log(f"Battle error: {e}")
                time.sleep(1)

        won  = result == "win"
        arch = archetype.archetype

        # Feed placements into PlacementDB
        for p in replay.placements:
            PLACEMENT_DB.record(p["card_name"], p["battle_phase"], p["lane"],
                                p["x_norm"], p["y_norm"], won)
        PLACEMENT_DB.save()

        # Feed card sequences into ComboTracker
        prev = ""
        for p in replay.placements:
            if prev:
                COMBO_DB.record(prev, p["card_name"], p["battle_phase"], won)
            prev = p["card_name"]
        COMBO_DB.save()

        # Feed wait events into WaitDB
        WAIT_DB.record_battle(replay.wait_events)
        WAIT_DB.save()

        db_summary = PLACEMENT_DB.summary()
        if db_summary:
            self.log(f"📊 PlacementDB: {len(db_summary)} keys learned  "
                     f"| arch={arch}")

        replay.save_local(result, reward.events, arch)
        ok = replay.send_to_worker(result, reward.events, arch)
        self.log(
            f"{'✅' if ok else '⚠️'} Replay synced "
            f"({len(replay.placements)} placements, "
            f"{len(replay.tower_hp_timeline)} HP snapshots, "
            f"{len(reward.events)} reward events)"
        )

        if result == "win":
            self.wins += 1
        else:
            self.losses += 1
        self.battles_played += 1

        self.dismiss_result()
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

        while self.running:
            try:
                screen = screenshot()

                if is_in_battle(screen):
                    self._battle_confirm += 1
                    if self._battle_confirm >= BATTLE_DEBOUNCE:
                        self._battle_confirm = 0
                        self.play_battle()
                elif is_on_home_screen(screen):
                    self._battle_confirm = 0
                    self.log("🏠 Home screen — starting battle!")
                    self.find_and_tap_battle(screen)
                    wait = random.randint(20, 45)
                    self.log(f"⏳ Matchmaking... waiting {wait}s")
                    time.sleep(wait)
                elif is_matchmaking(screen):
                    self._battle_confirm = 0
                    self.log("⏳ Matchmaking queue...")
                    time.sleep(5)
                elif is_loading(screen):
                    self._battle_confirm = 0
                    self.log("⏳ Loading...")
                    time.sleep(3)
                else:
                    self._battle_confirm = 0
                    self.log("🔍 Unknown screen — debug screenshot saved")
                    save_screenshot(r"C:\debug_screen.png")
                    time.sleep(3)

                time.sleep(random.uniform(2, 5))

                if self.battles_played > 0 and self.battles_played % 10 == 0:
                    brk = random.randint(120, 300)
                    self.log(f"☕ Anti-detection break: {brk}s")
                    time.sleep(brk)

            except Exception as e:
                self.log(f"Main loop error: {e}")
                time.sleep(5)

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
            except FileNotFoundError:
                pass
            except Exception as e:
                print(f"Config load error: {e}")

        def _save_config(self):
            try:
                os.makedirs(REPLAY_DIR, exist_ok=True)
                with open(self._CONFIG_PATH, "w") as f:
                    json.dump({"player_tag": self.tag_entry.get().strip()}, f)
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

            self.bot = RoyaleBot(on_status=self.log)
            self.thread = threading.Thread(target=self.bot.run, daemon=True)
            self.thread.start()
            self.dot.configure(text_color="#4caf50")
            self.status_lbl.configure(text="Running")
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
            self.log(f"🤖 Bot started! Tag: #{PLAYER_TAG}")

        def stop(self):
            if self.bot:
                self.bot.stop()
            self.dot.configure(text_color="#ff5252")
            self.status_lbl.configure(text="Stopped")
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self.tag_entry.configure(state="normal")
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
