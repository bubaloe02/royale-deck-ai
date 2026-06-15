import cv2
import numpy as np
import time
import random
import requests
import subprocess
import json
import os
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

# ─── DECK CONFIG ─────────────────────────────────────────────────────────────
# Your 8-card deck in cycle order (slot 0-3 = starting hand).
# Replace with your actual cards — used for rotation tracking + dispatch.
MY_DECK = [
    "slot_0",   # starting hand slot 0  ← replace: e.g. "Hog Rider"
    "slot_1",   # starting hand slot 1
    "slot_2",   # starting hand slot 2
    "slot_3",   # starting hand slot 3
    "slot_4",   # 5th card (drawn after slot 0 played)
    "slot_5",
    "slot_6",
    "slot_7",
]

# ─── CARD TYPE REGISTRY ──────────────────────────────────────────────────────
CARD_TYPES = {
    "Knight": "troop", "Hog Rider": "troop", "Musketeer": "troop",
    "Mini P.E.K.K.A": "troop", "Valkyrie": "troop", "Baby Dragon": "troop",
    "Mega Minion": "troop", "Prince": "troop", "Giant": "troop",
    "Goblin Gang": "troop", "Skeleton Army": "troop", "Ice Spirit": "troop",
    "Goblin": "troop", "Archer": "troop", "Minion Horde": "troop",
    "Electro Wizard": "troop", "Witch": "troop", "Lumberjack": "troop",
    "Tesla": "building", "Cannon": "building", "Inferno Tower": "building",
    "Bomb Tower": "building", "X-Bow": "building", "Mortar": "building",
    "Fireball": "spell", "Arrows": "spell", "Zap": "spell",
    "Lightning": "spell", "Rocket": "spell", "Goblin Barrel": "spell",
    "Freeze": "spell", "Poison": "spell", "Log": "spell",
}

def card_type(card_name):
    return CARD_TYPES.get(card_name, "troop")

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
    Tracks which card is in each of the 4 hand slots across the 8-card cycle.
    When a slot is played, the next card from the cycle enters that slot.

    With template matching: card names are real.
    Without it: slot_0..slot_7 are used as placeholders.
    """
    def __init__(self, deck=None):
        if deck is None:
            deck = MY_DECK
        self.deck       = list(deck)
        self.hand       = list(deck[:4])
        self._cycle_pos = 4   # next card to draw from deck

    def play(self, slot):
        """Mark slot as played; pull next card from cycle into it."""
        played = self.hand[slot]
        next_card = self.deck[self._cycle_pos % len(self.deck)]
        self._cycle_pos += 1
        self.hand[slot] = next_card
        return played

    def card_at(self, slot):
        return self.hand[slot]

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
    return x, y

def place_troop(card_name, phase, lane: LanePressureTracker, w, h):
    """Bridge pressure during attack; defend hot lane when threatened."""
    if phase == PHASE_DEFENDING and lane.hot_lane:
        pool = (["defense_left", "support_left"] if lane.hot_lane == "left"
                else ["defense_right", "support_right"])
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

def place_spell(card_name, phase, lane: LanePressureTracker, game_time, w, h):
    """
    Spells target enemy territory, preferring the hot lane.
    Skip entirely if game is too early and there's no meaningful target.
    Returns None if spell should be held.
    """
    if game_time < 20:
        return None   # no clump yet — don't waste it

    if lane.hot_lane == "left":
        pool = ["spell_left", "push_left"]
    elif lane.hot_lane == "right":
        pool = ["spell_right", "push_right"]
    else:
        pool = ["spell_left", "spell_right", "spell_center"]

    return _tile(random.choice(pool), w, h)

def get_play_position(card_name, phase, lane_pressure, game_time, w, h):
    """
    Dispatch to card-type-specific handler.
    Returns (x, y) or None (meaning: don't play this card right now).
    """
    ctype = card_type(card_name)
    if ctype == "troop":
        return place_troop(card_name, phase, lane_pressure, w, h)
    elif ctype == "building":
        return place_building(card_name, phase, lane_pressure, w, h)
    elif ctype == "spell":
        return place_spell(card_name, phase, lane_pressure, game_time, w, h)
    return place_troop(card_name, phase, lane_pressure, w, h)

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
        self.events.append({
            **placement,
            "our_tower_dmg":   round(our_dmg,   2),
            "their_tower_dmg": round(their_dmg, 2),
            "elixir_spent":    elixir_spent,
            # EV placeholder — will be set by future reward model
            "ev": None,
        })

# ─── REPLAY LOGGER ───────────────────────────────────────────────────────────

class ReplayLogger:
    HP_SAMPLE_INTERVAL = 10

    def __init__(self, screen_w, screen_h):
        ts = datetime.now(timezone.utc)
        self.battle_id  = f"bot_{ts.strftime('%Y%m%d_%H%M%S')}_{random.randint(1000,9999)}"
        self.started_at = ts.isoformat()
        self.screen_w   = screen_w
        self.screen_h   = screen_h
        self.our_deck   = list(MY_DECK[:4])
        self.placements        = []
        self.tower_hp_timeline = []
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
                      elixir, phase, battle_phase):
        x_norm = round(tx / self.screen_w, 3)
        y_norm = round(ty / self.screen_h, 3)
        entry = {
            "card_slot":    card_slot,
            "card_name":    card_name,
            "card_type":    card_type(card_name),
            "game_time_ms": self.elapsed_ms(),
            "x_norm":       x_norm,
            "y_norm":       y_norm,
            "lane":         classify_lane(x_norm),
            "side":         "ours",
            "elixir":       elixir,
            "phase":        phase,
            "battle_phase": battle_phase,
        }
        self.placements.append(entry)
        return entry

    def to_dict(self, result="unknown", reward_events=None):
        return {
            "battle_id":         self.battle_id,
            "started_at":        self.started_at,
            "result":            result,
            "duration_ms":       self.elapsed_ms(),
            "source":            "bot_mumu",
            "our_deck":          self.our_deck,
            "placements":        self.placements,
            "tower_hp_timeline": self.tower_hp_timeline,
            "reward_events":     reward_events or [],
        }

    def save_local(self, result="unknown", reward_events=None):
        os.makedirs(REPLAY_DIR, exist_ok=True)
        path = os.path.join(REPLAY_DIR, f"{self.battle_id}.json")
        with open(path, "w") as f:
            json.dump(self.to_dict(result, reward_events), f, indent=2)
        print(f"Replay saved → {path}")
        return path

    def send_to_worker(self, result="unknown", reward_events=None):
        try:
            res = requests.post(
                f"{WORKER_URL}/bot/battle",
                json=self.to_dict(result, reward_events),
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
        replay   = ReplayLogger(self.screen_w, self.screen_h)
        rotation = CardRotation()
        state    = BattleStateMachine()
        lane_p   = LanePressureTracker()
        enemy_ex = EnemyElixirTracker()
        reward   = RewardEngine()

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

                elixir = get_elixir(screen)

                if DEBUG:
                    self.log(
                        f"💧 {elixir}/10  t={int(game_time)}s  "
                        f"phase={state.phase}  "
                        f"lane L={lane_p.left:.0f} R={lane_p.right:.0f}  "
                        f"enemy_ex≈{enemy_ex.estimate:.1f}  "
                        f"hand={rotation.hand}"
                    )

                # Decide whether to play
                cooldown_ok = time.time() - last_play_t >= play_cooldown
                elixir_ok   = elixir >= 4 or DEBUG_FORCE_PLAY
                skip_rand   = (not DEBUG_FORCE_PLAY) and random.random() < 0.20

                if cooldown_ok and elixir_ok and not skip_rand:
                    slot      = cards_played % 4
                    card_name = rotation.card_at(slot)
                    ctype     = card_type(card_name)
                    phase_str = "early" if game_time < 90 else "double"

                    pos = get_play_position(card_name, state.phase, lane_p,
                                            game_time, w, h)

                    if pos is None:
                        self.log(f"⏭️ Hold {card_name} ({ctype}): no valid target")
                    else:
                        tx, ty = pos
                        cx, cy = card_positions[slot]

                        hp_before = dict(hp)
                        drag(cx, cy, tx, ty, duration_ms=150)
                        rotation.play(slot)

                        x_n = round(tx / w, 3)
                        entry = replay.log_placement(
                            slot, card_name, tx, ty,
                            elixir, phase_str, state.phase
                        )

                        # Collect reward data after a short settle window
                        time.sleep(0.5)
                        scr2 = screenshot()
                        hp_after = sample_tower_hp(scr2)
                        reward.record(entry, hp_before, hp_after, elixir)

                        last_play_t   = time.time()
                        play_cooldown = human_play_interval()
                        cards_played += 1

                        self.log(
                            f"🃏 {card_name} [{ctype}] "
                            f"({cx},{cy})→({tx},{ty}) "
                            f"lane={classify_lane(x_n)} "
                            f"elixir={elixir} phase={state.phase}"
                        )

                time.sleep(random.uniform(0.3, 0.7))

            except Exception as e:
                self.log(f"Battle error: {e}")
                time.sleep(1)

        replay.save_local(result, reward.events)
        ok = replay.send_to_worker(result, reward.events)
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
            self.root.geometry("500x640")
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
            self.bot = RoyaleBot(on_status=self.log)
            self.thread = threading.Thread(target=self.bot.run, daemon=True)
            self.thread.start()
            self.dot.configure(text_color="#4caf50")
            self.status_lbl.configure(text="Running")
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
            self.log("🤖 Bot started!")

        def stop(self):
            if self.bot:
                self.bot.stop()
            self.dot.configure(text_color="#ff5252")
            self.status_lbl.configure(text="Stopped")
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
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
