import subprocess
import os
import shutil
import glob

REPOS = [
    ("https://github.com/pyclashbot/py-clash-bot.git", r"C:\py-clash-bot"),
    ("https://github.com/jlaiii/TKH.git",              r"C:\TKH"),
]
TEMPLATES_DIR = r"C:\templates"

os.makedirs(TEMPLATES_DIR, exist_ok=True)

for url, dest in REPOS:
    if os.path.exists(dest):
        print(f"[skip] {dest} already exists — not re-cloning")
    else:
        print(f"[clone] {url} → {dest}")
        result = subprocess.run(
            f'git clone --depth 1 "{url}" "{dest}"',
            capture_output=True, text=True, shell=True
        )
        if result.returncode != 0:
            print(f"  ERROR: {result.stderr.strip()}")
        else:
            print(f"  OK")

copied = []
for _, repo_dir in REPOS:
    for src in glob.glob(os.path.join(repo_dir, "**", "*.png"), recursive=True):
        filename = os.path.basename(src)
        dst = os.path.join(TEMPLATES_DIR, filename)
        # Keep the first file if names collide; rename duplicates
        if os.path.exists(dst):
            repo_name = os.path.basename(repo_dir)
            dst = os.path.join(TEMPLATES_DIR, f"{repo_name}_{filename}")
        shutil.copy2(src, dst)
        copied.append(os.path.basename(dst))

print(f"\n[done] Copied {len(copied)} PNG files to {TEMPLATES_DIR}")
for name in sorted(copied):
    print(f"  {name}")
