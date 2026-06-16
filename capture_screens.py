import subprocess
import time
import os
from datetime import datetime

ADB = r"C:\adb\platform-tools\adb.exe"
DEVICE = "127.0.0.1:7555"
OUT_DIR = r"C:\captures"
INTERVAL_SEC = 3

os.makedirs(OUT_DIR, exist_ok=True)

print("Capturing a screenshot every " + str(INTERVAL_SEC) + " seconds to " + OUT_DIR)
print("Play through a full match now (menu -> battle -> victory/defeat -> chest claim).")
print("Press Ctrl+C to stop.")
print("")

count = 0
try:
    while True:
        result = subprocess.run(
            [ADB, "-s", DEVICE, "exec-out", "screencap", "-p"],
            capture_output=True
        )
        if result.returncode != 0 or not result.stdout:
            print("  [warn] capture failed: " + result.stderr.decode(errors="ignore"))
        else:
            ts = datetime.now().strftime("%H%M%S")
            path = os.path.join(OUT_DIR, "screen_" + ts + ".png")
            with open(path, "wb") as f:
                f.write(result.stdout)
            count += 1
            print("  [" + str(count) + "] saved " + path)
        time.sleep(INTERVAL_SEC)
except KeyboardInterrupt:
    print("")
    print("[done] Captured " + str(count) + " screenshots to " + OUT_DIR)
