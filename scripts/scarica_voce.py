"""Scarica la voce italiana di Piper (gratuita, ~60 MB) nella cartella voices/."""
from pathlib import Path
from urllib.request import urlretrieve

BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/paola/medium/"
FILES = ["it_IT-paola-medium.onnx", "it_IT-paola-medium.onnx.json"]

dest = Path(__file__).resolve().parent.parent / "voices"
dest.mkdir(exist_ok=True)
for name in FILES:
    target = dest / name
    if target.exists():
        print(f"già presente: {name}")
        continue
    print(f"scarico {name}…")
    urlretrieve(BASE + name, target)
print("Voce pronta in", dest)
