import urllib.request
import zipfile
import io
import os
import shutil

REPOS = [
    ("https://github.com/pyclashbot/py-clash-bot/archive/HEAD.zip",
     "C:\\py-clash-bot"),
    ("https://github.com/jlaiii/TKH/archive/HEAD.zip",
     "C:\\TKH"),
]
TEMPLATES_DIR = "C:\\templates"

os.makedirs(TEMPLATES_DIR, exist_ok=True)

for url, dest in REPOS:
    if os.path.exists(dest):
        print("[skip] " + dest + " already exists")
    else:
        print("[download] " + url)
        try:
            resp = urllib.request.urlopen(url, timeout=60)
            data = resp.read()
            resp.close()
            print("  downloaded " + str(len(data) // 1024) + " KB - extracting...")
            zf = zipfile.ZipFile(io.BytesIO(data))
            zf.extractall(os.path.dirname(dest))
            zf.close()
            parent = os.path.dirname(dest)
            for item in os.listdir(parent):
                full = os.path.join(parent, item)
                repo_base = os.path.basename(dest).lower()
                if item.lower().startswith(repo_base) and os.path.isdir(full):
                    if not os.path.exists(dest):
                        os.rename(full, dest)
                        break
            print("  OK - " + dest)
        except Exception as e:
            print("  ERROR: " + str(e))

copied = []
for url, repo_dir in REPOS:
    if not os.path.exists(repo_dir):
        print("[warn] " + repo_dir + " missing - skipping")
        continue
    for root, dirs, files in os.walk(repo_dir):
        for fname in files:
            if fname.lower().endswith(".png"):
                src = os.path.join(root, fname)
                dst = os.path.join(TEMPLATES_DIR, fname)
                if os.path.exists(dst):
                    repo_name = os.path.basename(repo_dir)
                    dst = os.path.join(TEMPLATES_DIR, repo_name + "_" + fname)
                shutil.copy2(src, dst)
                copied.append(os.path.basename(dst))

print("")
print("[done] Copied " + str(len(copied)) + " PNG files to " + TEMPLATES_DIR)
for name in sorted(copied):
    print("  " + name)
