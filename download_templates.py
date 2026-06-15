import urllib.request
import zipfile
import os
import shutil
import io

REPOS = [
    ("https://github.com/pyclashbot/py-clash-bot/archive/refs/heads/main.zip", r"C:\py-clash-bot"),
    ("https://github.com/jlaiii/TKH/archive/refs/heads/main.zip",              r"C:\TKH"),
]
TEMPLATES_DIR = r"C:\templates"

os.makedirs(TEMPLATES_DIR, exist_ok=True)

for url, dest in REPOS:
    if os.path.exists(dest):
        print(f"[skip] {dest} already exists")
    else:
        print(f"[download] {url}")
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                data = resp.read()
            print(f"  downloaded {len(data)//1024} KB — extracting...")
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                zf.extractall(os.path.dirname(dest))
            # GitHub zips extract as <repo>-main — rename to dest
            extracted = [
                os.path.join(os.path.dirname(dest), d)
                for d in os.listdir(os.path.dirname(dest))
                if d.endswith("-main") and os.path.isdir(
                    os.path.join(os.path.dirname(dest), d))
            ]
            for folder in extracted:
                if not os.path.exists(dest):
                    os.rename(folder, dest)
                    break
            print(f"  OK → {dest}")
        except Exception as e:
            print(f"  ERROR: {e}")

copied = []
for _, repo_dir in REPOS:
    if not os.path.exists(repo_dir):
        print(f"[warn] {repo_dir} missing — skipping PNG copy")
        continue
    for root, _, files in os.walk(repo_dir):
        for fname in files:
            if fname.lower().endswith(".png"):
                src = os.path.join(root, fname)
                dst = os.path.join(TEMPLATES_DIR, fname)
                if os.path.exists(dst):
                    repo_name = os.path.basename(repo_dir)
                    dst = os.path.join(TEMPLATES_DIR, f"{repo_name}_{fname}")
                shutil.copy2(src, dst)
                copied.append(os.path.basename(dst))

print(f"\n[done] Copied {len(copied)} PNG files to {TEMPLATES_DIR}")
for name in sorted(copied):
    print(f"  {name}")
