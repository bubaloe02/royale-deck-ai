import cv2
import numpy as np
import time
import random
import requests
import subprocess
from PIL import Image
import io
import threading
from datetime import datetime

# ─── CONFIG ──────────────────────────────────────────────────────────────────
WORKER_URL = "https://small-king-a65c.jared1999.workers.dev"
ADB = r"C:\adb\platform-tools\adb.exe"
DEVICE = "127.0.0.1:7555"

# ─── DEBUG FLAGS (set all True while tuning, False for live play) ─────────────
DEBUG             = True   # verbose elixir + coordinate logging  (#3)
DEBUG_FORCE_PLAY  = True   # ignore elixir/cooldown, always play  (#4)
DEBUG_NO_JITTER   = True   # disable tap jitter                   (#8)
DEBUG_SAVE_COORDS = True   # write coord overlay on first battle  (#2)
BATTLE_DEBOUNCE   = 2      # consecutive frames needed to confirm battle (#7)

# ─── ADB CONTROLLER ──────────────────────────────────────────────────────────

def adb_cmd(cmd_list):
    return subprocess.run([ADB, "-s", DEVICE] + cmd_list, capture_output=True)

def _jitter():
    return (0, 0) if DEBUG_NO_JITTER else (random.randint(-3, 3), random.randint(-3, 3))

def tap(x, y):
    jx, jy = _jitter()
    adb_cmd(["shell", "input", "tap", str(x + jx), str(y + jy)])
    time.sleep(random.uniform(0.05, 0.15))

def drag(x1, y1, x2, y2, duration_ms=400):
    """Swipe from card slot to arena position — required for CR card placement."""
    jx, jy = _jitter()
    adb_cmd([
        "shell", "input", "swipe",
        str(x1 + jx), str(y1 + jy),
        str(x2), str(y2),
        str(duration_ms),
    ])
    time.sleep(random.uniform(0.1, 0.25))

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

def save_coord_overlay(screen, card_positions, play_samples, path=r"C:\debug_coords.png"):
    """Draw card slots (green) and arena targets (red) on a screenshot."""
    img = screen.copy()
    for idx, (cx, cy) in card_positions.items():
        cv2.circle(img, (cx, cy), 18, (0, 255, 0), 3)
        cv2.putText(img, f"C{idx}", (cx - 12, cy - 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    for (px, py) in play_samples:
        cv2.circle(img, (px, py), 12, (0, 0, 255), 2)
        cv2.putText(img, "X", (px - 7, py + 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    cv2.imwrite(path, img)
    print(f"Coord overlay saved to {path}")

# ─── SCREEN DETECTION ────────────────────────────────────────────────────────
# All regions use proportional coordinates so the bot works at any resolution.

def is_on_home_screen(screen):
    """Battle button: golden-yellow band in lower-center of screen."""
    h, w = screen.shape[:2]
    region = screen[int(h * 0.65):int(h * 0.90), int(w * 0.20):int(w * 0.80)]
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv, (18, 160, 160), (38, 255, 255))
    return cv2.countNonZero(yellow) > 400

def _elixir_purple_count(screen):
    """Raw purple pixel count in the elixir bar region."""
    h, w = screen.shape[:2]
    region = screen[int(h * 0.86):int(h * 0.93), int(w * 0.05):int(w * 0.55)]
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    purple = cv2.inRange(hsv, (130, 60, 60), (160, 255, 255))
    return cv2.countNonZero(purple)

def is_in_battle(screen):
    """Purple elixir bar present at bottom-left → we are in a battle."""
    return _elixir_purple_count(screen) > 80

def is_battle_ended(screen):
    """Victory/Defeat banner floods center with bright pixels."""
    h, w = screen.shape[:2]
    region = screen[int(h * 0.20):int(h * 0.50), int(w * 0.10):int(w * 0.90)]
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    bright = cv2.countNonZero(cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)[1])
    return bright > region.shape[0] * region.shape[1] * 0.30

def did_win(screen):
    """More golden crown pixels on our half than theirs."""
    h, w = screen.shape[:2]
    ours   = screen[int(h*0.02):int(h*0.08), int(w*0.05):int(w*0.40)]
    theirs = screen[int(h*0.02):int(h*0.08), int(w*0.60):int(w*0.95)]
    our_g   = cv2.countNonZero(cv2.inRange(ours,   (0, 150, 150), (50, 255, 255)))
    their_g = cv2.countNonZero(cv2.inRange(theirs, (0, 150, 150), (50, 255, 255)))
    return our_g > their_g

def get_elixir(screen):
    """Estimate elixir 0-10 from purple pixel count in elixir bar."""
    return min(10, int(_elixir_purple_count(screen) / 15))

def is_loading(screen):
    h, w = screen.shape[:2]
    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    very_dark = cv2.countNonZero(cv2.threshold(gray, 20, 255, cv2.THRESH_BINARY_INV)[1])
    return very_dark > (w * h * 0.7)

def is_matchmaking(screen):
    """Red cancel button at bottom-center → waiting for opponent."""
    h, w = screen.shape[:2]
    region = screen[int(h * 0.78):int(h * 0.90), int(w * 0.25):int(w * 0.75)]
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    red1 = cv2.inRange(hsv, (0,   150, 150), (10,  255, 255))
    red2 = cv2.inRange(hsv, (170, 150, 150), (180, 255, 255))
    return cv2.countNonZero(red1) + cv2.countNonZero(red2) > 200

# ─── PROPORTIONAL COORDINATES ────────────────────────────────────────────────

def get_card_tap_positions(w, h):
    """Four card slots at the bottom of a portrait screen."""
    y = int(h * 0.885)
    return {
        0: (int(w * 0.18), y),
        1: (int(w * 0.36), y),
        2: (int(w * 0.54), y),
        3: (int(w * 0.72), y),
    }

# Arena playfield bounds (proportion of screen): x 5-95%, y 15-80%
ARENA_X_MIN, ARENA_X_MAX = 0.05, 0.95
ARENA_Y_MIN, ARENA_Y_MAX = 0.15, 0.80

def get_play_position(game_time, w, h):
    """Random legal arena target, proportional to screen size."""
    if game_time < 90:
        positions = [
            (0.50, 0.62), (0.38, 0.60), (0.62, 0.60),
            (0.50, 0.70), (0.38, 0.68), (0.62, 0.68),
        ]
    else:
        positions = [
            (0.50, 0.52), (0.38, 0.50), (0.62, 0.50),
            (0.50, 0.58), (0.38, 0.56), (0.62, 0.56),
        ]
    px, py = random.choice(positions)
    x = int(px * w) + (0 if DEBUG_NO_JITTER else random.randint(-15, 15))
    y = int(py * h) + (0 if DEBUG_NO_JITTER else random.randint(-10, 10))

    # Clamp to legal arena bounds (#6)
    x = max(int(ARENA_X_MIN * w), min(int(ARENA_X_MAX * w), x))
    y = max(int(ARENA_Y_MIN * h), min(int(ARENA_Y_MAX * h), y))
    return x, y

def should_play(elixir, last_play_time, cards_played):
    if DEBUG_FORCE_PLAY:
        return True, cards_played % 4
    if elixir < 4:
        return False, None
    if time.time() - last_play_time < 2.0:
        return False, None
    if random.random() < 0.25:
        return False, None
    return True, cards_played % 4

# ─── BATTLE STATE ────────────────────────────────────────────────────────────

class BattleState:
    def __init__(self):
        self.battle_id = f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000,9999)}"
        self.placements = []
        self.start_time = time.time()
        self.last_play_time = 0
        self.cards_played = 0

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
        self._battle_confirm = 0   # debounce counter (#7)
        self._coords_saved = False

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}")
        if self.on_status:
            self.on_status(msg)

    def send_data(self, state, won):
        try:
            payload = {
                "battle_id": state.battle_id,
                "won": won,
                "placements": state.placements,
                "duration_ms": int((time.time() - state.start_time) * 1000),
                "source": "bot_mumu",
            }
            res = requests.post(f"{WORKER_URL}/bot/battle", json=payload, timeout=10)
            if res.ok:
                self.log("✅ Data sent to Royale Deck AI")
        except Exception as e:
            self.log(f"⚠️ Send error: {e}")

    def find_and_tap_battle(self, screen):
        h, w = screen.shape[:2]
        bx, by = int(w * 0.40), int(h * 0.77)
        self.log(f"🎮 Tapping battle button at ({bx}, {by}) on {w}x{h}...")
        tap(bx, by)
        time.sleep(2)

    def dismiss_result(self):
        w, h = self.screen_w, self.screen_h
        time.sleep(2)
        tap(int(w * 0.50), int(h * 0.60))
        time.sleep(1)
        tap(int(w * 0.50), int(h * 0.65))
        time.sleep(2)

    def play_battle(self):
        state = BattleState()
        self.log(f"⚔️ Battle #{self.battles_played + 1} started!")
        battle_start = time.time()
        w, h = self.screen_w, self.screen_h
        card_positions = get_card_tap_positions(w, h)
        self.log(f"🃏 Card slots: { {k: v for k, v in card_positions.items()} }")

        # Save coordinate overlay once so positions can be verified visually (#2)
        if DEBUG_SAVE_COORDS and not self._coords_saved:
            try:
                screen0 = screenshot()
                samples = [get_play_position(0, w, h) for _ in range(6)]
                save_coord_overlay(screen0, card_positions, samples)
                self._coords_saved = True
            except Exception as e:
                self.log(f"Coord overlay error: {e}")

        while time.time() - battle_start < 250:
            if not self.running:
                break
            try:
                screen = screenshot()   # single capture, reused for all checks (#9)

                if is_battle_ended(screen):
                    won = did_win(screen)
                    self.log(f"{'🏆 WIN' if won else '💀 LOSS'}!")
                    self.send_data(state, won)
                    if won:
                        self.wins += 1
                    else:
                        self.losses += 1
                    self.battles_played += 1
                    self.dismiss_result()
                    return won

                if not is_in_battle(screen):
                    time.sleep(1)
                    continue

                elixir = get_elixir(screen)
                game_time = time.time() - state.start_time

                if DEBUG:
                    purple_px = _elixir_purple_count(screen)
                    self.log(f"💧 Elixir: {elixir}/10  (purple_px={purple_px})  t={int(game_time)}s")

                should, card_idx = should_play(elixir, state.last_play_time, state.cards_played)

                if should and card_idx is not None:
                    phase = "early" if game_time < 90 else "double"
                    cx, cy = card_positions[card_idx]
                    tx, ty = get_play_position(game_time, w, h)

                    # Validate arena bounds before sending (#6)
                    legal = (ARENA_X_MIN * w <= tx <= ARENA_X_MAX * w and
                             ARENA_Y_MIN * h <= ty <= ARENA_Y_MAX * h)
                    if not legal:
                        self.log(f"⚠️ Target ({tx},{ty}) outside arena bounds — skipping")
                        continue

                    # Drag from card slot to arena position (#1)
                    drag(cx, cy, tx, ty, duration_ms=400)

                    state.placements.append({
                        "card_slot": card_idx,
                        "x": round(tx / w, 3),
                        "y": round(ty / h, 3),
                        "elixir_at_play": elixir,
                        "game_time_ms": int(game_time * 1000),
                        "phase": phase,
                    })
                    state.last_play_time = time.time()
                    state.cards_played += 1
                    self.log(f"🃏 Card {card_idx} dragged ({cx},{cy})→({tx},{ty}) | Elixir: {elixir} | {phase}")

                time.sleep(random.uniform(0.4, 0.9))

            except Exception as e:
                self.log(f"Battle error: {e}")
                time.sleep(1)

        return False

    def run(self):
        self.running = True
        self.log("🤖 RoyaleBot started!")
        if DEBUG:
            self.log(f"🐛 DEBUG mode ON | FORCE_PLAY={DEBUG_FORCE_PLAY} | NO_JITTER={DEBUG_NO_JITTER}")
        subprocess.run([ADB, "connect", DEVICE], capture_output=True)
        time.sleep(1)

        # Detect and log screen resolution (#5)
        first = screenshot()
        self.screen_h, self.screen_w = first.shape[:2]
        self.log(f"📐 Screen detected: {self.screen_w}x{self.screen_h}")

        while self.running:
            try:
                screen = screenshot()   # one capture per main-loop iteration (#9)

                # Debounced battle detection (#7)
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
                    self.log("⏳ In matchmaking queue...")
                    time.sleep(5)
                elif is_loading(screen):
                    self._battle_confirm = 0
                    self.log("⏳ Loading...")
                    time.sleep(3)
                else:
                    self._battle_confirm = 0
                    self.log("🔍 Unknown screen — saving debug screenshot...")
                    save_screenshot(r"C:\debug_screen.png")
                    time.sleep(3)

                time.sleep(random.uniform(2, 5))

                if self.battles_played > 0 and self.battles_played % 10 == 0:
                    long_break = random.randint(120, 300)
                    self.log(f"☕ Anti-detection break: {long_break}s")
                    time.sleep(long_break)

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
            self.bot = None
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
            ctk.CTkLabel(header, text="MuMu Player · Port 7555 · Anti-detection active",
                font=("Arial", 11), text_color="#333").pack(pady=2)

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
            ctk.CTkLabel(lf, text="BOT LOG", font=("Arial", 10, "bold"), text_color="#333").pack(anchor="w", padx=8, pady=4)
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

            ctk.CTkButton(self.root, text="📸 Debug Screenshot → C:\\debug_screen.png",
                font=("Arial", 11), fg_color="#1a1a2e", hover_color="#222244",
                command=self.take_screenshot, height=32).pack(pady=5, padx=20, fill="x")

            ctk.CTkLabel(self.root, text="Data syncs to royale-deck-ai database · Skrime VPS",
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
