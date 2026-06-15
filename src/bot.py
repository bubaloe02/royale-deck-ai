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
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720

# Card hand positions (bottom of screen)
CARD_POSITIONS = {
    0: (320, 650),
    1: (427, 650),
    2: (534, 650),
    3: (641, 650),
}

# ─── ADB CONTROLLER ──────────────────────────────────────────────────────────

def adb_cmd(cmd_list):
    result = subprocess.run(
        [ADB, "-s", DEVICE] + cmd_list,
        capture_output=True
    )
    return result

def tap(x, y):
    jitter_x = random.randint(-3, 3)
    jitter_y = random.randint(-3, 3)
    adb_cmd(["shell", "input", "tap", str(x + jitter_x), str(y + jitter_y)])
    time.sleep(random.uniform(0.05, 0.15))

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

# ─── SCREEN DETECTION ────────────────────────────────────────────────────────

def is_on_home_screen(screen):
    """
    Detect the Battle button by its golden-yellow color using HSV.

    The button occupies the lower-center portion of the screen.
    HSV hue ~20-35 (orange-yellow), high saturation and brightness.
    Using proportional coordinates so this works at any device resolution.
    """
    h, w = screen.shape[:2]

    # Lower-center strip where the Battle button lives (~65-90% height, 20-80% width)
    y1, y2 = int(h * 0.65), int(h * 0.90)
    x1, x2 = int(w * 0.20), int(w * 0.80)
    battle_region = screen[y1:y2, x1:x2]

    hsv = cv2.cvtColor(battle_region, cv2.COLOR_BGR2HSV)

    # Golden-yellow: hue 18–38, saturation >160, value >160
    yellow_mask = cv2.inRange(hsv, (18, 160, 160), (38, 255, 255))

    pixel_count = cv2.countNonZero(yellow_mask)
    return pixel_count > 400


def is_in_battle(screen):
    """Check if in battle by looking for purple elixir bar"""
    elixir_region = screen[670:710, 40:360]
    purple_mask = cv2.inRange(elixir_region, (80, 0, 80), (220, 80, 220))
    return cv2.countNonZero(purple_mask) > 100

def is_battle_ended(screen):
    """Check if battle result screen showing"""
    result_region = screen[200:350, 350:930]
    gray = cv2.cvtColor(result_region, cv2.COLOR_BGR2GRAY)
    bright = cv2.countNonZero(cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)[1])
    return bright > 5000

def did_win(screen):
    """Determine if we won by comparing crown counts"""
    our_crowns = screen[30:80, 100:400]
    their_crowns = screen[30:80, 880:1180]
    our_gold = cv2.countNonZero(cv2.inRange(our_crowns, (0, 150, 150), (50, 255, 255)))
    their_gold = cv2.countNonZero(cv2.inRange(their_crowns, (0, 150, 150), (50, 255, 255)))
    return our_gold > their_gold

def get_elixir(screen):
    """Estimate elixir 0-10 from purple bar"""
    elixir_region = screen[680:700, 50:350]
    purple_mask = cv2.inRange(elixir_region, (100, 0, 100), (200, 50, 200))
    return min(10, int(cv2.countNonZero(purple_mask) / 30))

def is_loading(screen):
    """Check if screen is mostly dark (loading)"""
    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    very_dark = cv2.countNonZero(cv2.threshold(gray, 20, 255, cv2.THRESH_BINARY_INV)[1])
    return very_dark > (SCREEN_WIDTH * SCREEN_HEIGHT * 0.7)

def is_matchmaking(screen):
    """Check if in matchmaking lobby"""
    # Look for cancel button (red) at bottom
    cancel_region = screen[580:660, 450:830]
    red_mask = cv2.inRange(cancel_region, (0, 0, 150), (80, 80, 255))
    return cv2.countNonZero(red_mask) > 200

# ─── BATTLE LOGIC ────────────────────────────────────────────────────────────

class BattleState:
    def __init__(self):
        self.battle_id = f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000,9999)}"
        self.placements = []
        self.start_time = time.time()
        self.last_play_time = 0
        self.cards_played = 0

def get_play_position(card_index, elixir, game_time):
    """Rule-based placement strategy"""
    if game_time < 90:
        positions = [
            (640, 320), (580, 315), (700, 315),
            (640, 450), (580, 450), (700, 450),
        ]
    else:
        positions = [
            (640, 300), (580, 295), (700, 295),
            (640, 310), (600, 310), (680, 310),
        ]
    pos = random.choice(positions)
    return pos[0] + random.randint(-15, 15), pos[1] + random.randint(-10, 10)

def should_play(elixir, last_play_time, cards_played):
    """Decide whether to play a card"""
    if elixir < 4:
        return False, None
    if time.time() - last_play_time < 2.0:
        return False, None
    if random.random() < 0.25:
        return False, None
    return True, cards_played % 4

# ─── MAIN BOT ────────────────────────────────────────────────────────────────

class RoyaleBot:
    def __init__(self, on_status=None):
        self.running = False
        self.battles_played = 0
        self.wins = 0
        self.losses = 0
        self.on_status = on_status

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
        """Tap the battle button using proportional coordinates"""
        h, w = screen.shape[:2]
        # Battle button is at ~77% height, ~40% width (left of the trophy icon)
        bx = int(w * 0.40)
        by = int(h * 0.77)
        self.log(f"🎮 Tapping battle button at ({bx}, {by})...")
        tap(bx, by)
        time.sleep(2)

    def dismiss_result(self):
        """Dismiss battle result and return to home"""
        time.sleep(2)
        tap(640, 550)
        time.sleep(1)
        tap(640, 600)
        time.sleep(2)

    def play_battle(self):
        """Play one full battle"""
        state = BattleState()
        self.log(f"⚔️ Battle #{self.battles_played + 1} started!")
        battle_start = time.time()

        while time.time() - battle_start < 250:
            if not self.running:
                break
            try:
                screen = screenshot()

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
                should, card_idx = should_play(elixir, state.last_play_time, state.cards_played)

                if should and card_idx is not None:
                    phase = "early" if game_time < 90 else "double"
                    x, y = get_play_position(card_idx, elixir, game_time)

                    tap(CARD_POSITIONS[card_idx][0], CARD_POSITIONS[card_idx][1])
                    time.sleep(random.uniform(0.15, 0.35))
                    tap(x, y)

                    state.placements.append({
                        "card_slot": card_idx,
                        "x": round(x / SCREEN_WIDTH, 3),
                        "y": round(y / SCREEN_HEIGHT, 3),
                        "elixir_at_play": elixir,
                        "game_time_ms": int(game_time * 1000),
                        "phase": phase,
                    })

                    state.last_play_time = time.time()
                    state.cards_played += 1
                    self.log(f"🃏 Card {card_idx} → ({x},{y}) | Elixir: {elixir}")

                time.sleep(random.uniform(0.4, 0.9))

            except Exception as e:
                self.log(f"Battle error: {e}")
                time.sleep(1)

        return False

    def run(self):
        self.running = True
        self.log("🤖 RoyaleBot started!")
        subprocess.run([ADB, "connect", DEVICE], capture_output=True)
        time.sleep(1)

        while self.running:
            try:
                screen = screenshot()

                if is_in_battle(screen):
                    self.play_battle()
                elif is_on_home_screen(screen):
                    self.log("🏠 Home screen — starting battle!")
                    self.find_and_tap_battle(screen)
                    wait = random.randint(20, 45)
                    self.log(f"⏳ Matchmaking... waiting {wait}s")
                    time.sleep(wait)
                elif is_matchmaking(screen):
                    self.log("⏳ In matchmaking queue...")
                    time.sleep(5)
                elif is_loading(screen):
                    self.log("⏳ Loading...")
                    time.sleep(3)
                else:
                    self.log("🔍 Unknown screen — taking debug screenshot...")
                    save_screenshot(r"C:\debug_screen.png")
                    time.sleep(3)

                time.sleep(random.uniform(2, 5))

                # Long break every 10 battles
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

            # Header
            header = ctk.CTkFrame(self.root, fg_color="#0a0a1a", corner_radius=0)
            header.pack(fill="x")
            ctk.CTkLabel(header, text="👑 ROYALE BOT AI",
                font=("Arial", 24, "bold"), text_color="#ff6f00").pack(pady=10)
            ctk.CTkLabel(header, text="MuMu Player · Port 7555 · Anti-detection active",
                font=("Arial", 11), text_color="#333").pack(pady=2)

            # Status
            sf = ctk.CTkFrame(self.root, fg_color="#111122")
            sf.pack(fill="x", padx=20, pady=10)
            self.dot = ctk.CTkLabel(sf, text="⬤", font=("Arial", 16), text_color="#ff5252")
            self.dot.pack(side="left", padx=10, pady=8)
            self.status_lbl = ctk.CTkLabel(sf, text="Stopped", font=("Arial", 13))
            self.status_lbl.pack(side="left", pady=8)

            # Stats
            stats = ctk.CTkFrame(self.root, fg_color="#0d0d1f")
            stats.pack(fill="x", padx=20, pady=5)
            stats.grid_columnconfigure((0,1,2), weight=1)

            self.battles_var = ctk.StringVar(value="0")
            self.wins_var = ctk.StringVar(value="0")
            self.losses_var = ctk.StringVar(value="0")

            for i, (lbl, var, col) in enumerate([
                ("BATTLES", self.battles_var, "#ff9a40"),
                ("WINS", self.wins_var, "#4caf50"),
                ("LOSSES", self.losses_var, "#f44336"),
            ]):
                f = ctk.CTkFrame(stats, fg_color="#111133")
                f.grid(row=0, column=i, padx=5, pady=10, sticky="ew")
                ctk.CTkLabel(f, textvariable=var, font=("Arial", 30, "bold"), text_color=col).pack(pady=5)
                ctk.CTkLabel(f, text=lbl, font=("Arial", 10), text_color="#555").pack(pady=2)

            self.wr_var = ctk.StringVar(value="Win Rate: --%")
            ctk.CTkLabel(self.root, textvariable=self.wr_var,
                font=("Arial", 13), text_color="#ffd700").pack(pady=3)

            # Log
            lf = ctk.CTkFrame(self.root, fg_color="#050510")
            lf.pack(fill="both", expand=True, padx=20, pady=5)
            ctk.CTkLabel(lf, text="BOT LOG", font=("Arial", 10, "bold"), text_color="#333").pack(anchor="w", padx=8, pady=4)
            self.log_box = ctk.CTkTextbox(lf, font=("Courier", 11),
                fg_color="#030308", text_color="#4caf50", height=200)
            self.log_box.pack(fill="both", expand=True, padx=5, pady=5)

            # Buttons
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
