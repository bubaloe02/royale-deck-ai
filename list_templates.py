import os

TEMPLATES_DIR = "C:\\templates"

files = []
for root, dirs, names in os.walk(TEMPLATES_DIR):
    for name in names:
        if name.lower().endswith(".png"):
            full = os.path.join(root, name)
            size_kb = os.path.getsize(full) // 1024
            files.append((name, size_kb))

files.sort(key=lambda x: x[0].lower())

print("Found " + str(len(files)) + " PNG files in " + TEMPLATES_DIR)
print("")
for name, size_kb in files:
    print(name + "  (" + str(size_kb) + " KB)")
