"""Avvio di AGIS con un doppio clic (icona sul desktop / menu Start).

Gira con pythonw.exe, quindi senza finestra nera. Prima di aprire AGIS:
1. si aggiorna da GitHub (git pull), se c'è internet;
2. se sono cambiate le librerie richieste, le installa;
3. avvia l'app, scrivendo eventuali errori in data/agis.log.
Se qualcosa va storto mostra un messaggio invece di chiudersi in silenzio.
"""
from __future__ import annotations

import hashlib
import subprocess
import time
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOG = DATA / "agis.log"
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


def log(msg: str) -> None:
    DATA.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def message(title: str, text: str) -> None:
    """Finestra di avviso di Windows (funziona anche senza console)."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)
    else:
        print(f"{title}: {text}")


def run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                              timeout=timeout, creationflags=NO_WINDOW)
    except Exception as e:  # noqa: BLE001
        log(f"comando non riuscito {cmd[:3]}: {e}")
        return None


def requirements_hash() -> str:
    req = ROOT / "requirements.txt"
    return hashlib.sha256(req.read_bytes()).hexdigest() if req.exists() else ""


# File del programma che a volte risultano "modificati" sul PC (a capo Windows, o modificati
# da AGIS stesso): se bloccano l'aggiornamento se ne salva una copia e si ripristinano.
RESTORABLE = ("workspace/", "agis/", "scripts/", "requirements.txt", "config.example.toml")


def blocking_files(stderr: str) -> list[str]:
    """Estrae i file elencati da git in 'Your local changes ... would be overwritten'."""
    if "would be overwritten" not in stderr:
        return []
    files, grab = [], False
    for line in stderr.splitlines():
        if "would be overwritten" in line:
            grab = True
            continue
        if grab:
            name = line.strip()
            if not name or name.startswith(("Please", "Aborting")):
                break
            files.append(name)
    return files


def update() -> None:
    """Aggiornamento silenzioso: se fallisce (niente internet, modifiche locali) si va avanti."""
    before = requirements_hash()
    res = run(["git", "pull", "--ff-only", "--quiet"], timeout=25)
    if res is not None and res.returncode != 0:
        files = blocking_files(res.stderr)
        if files and all(f.startswith(RESTORABLE) for f in files):
            backup = DATA / "copie_locali" / time.strftime("%Y%m%d-%H%M%S")
            for f in files:
                src = ROOT / f
                if src.exists():
                    (backup / f).parent.mkdir(parents=True, exist_ok=True)
                    (backup / f).write_bytes(src.read_bytes())
            run(["git", "checkout", "--", *files], timeout=25)
            log(f"modifiche locali a {', '.join(files)} salvate in {backup} e ripristinate")
            res = run(["git", "pull", "--ff-only", "--quiet"], timeout=25)
    if res is not None:
        log(f"git pull: {'ok' if res.returncode == 0 else res.stderr.strip()[:300]}")
    stamp = DATA / ".requirements.sha256"
    now = requirements_hash()
    if now and (now != before or not stamp.exists() or stamp.read_text() != now):
        python = Path(sys.executable).with_name("python.exe") if sys.platform == "win32" else Path(sys.executable)
        res = run([str(python), "-m", "pip", "install", "-q", "-r", "requirements.txt"], timeout=900)
        if res is not None and res.returncode == 0:
            stamp.write_text(now)
            log("librerie aggiornate")
        elif res is not None:
            log(f"pip install non riuscito: {res.stderr.strip()[-500:]}")


def main() -> None:
    DATA.mkdir(exist_ok=True)
    # Senza console (pythonw) stdout/stderr non esistono: li mandiamo nel file di log.
    if sys.stdout is None or sys.stderr is None:
        stream = LOG.open("a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or stream
        sys.stderr = sys.stderr or stream
    log("--- avvio AGIS ---")
    if "--no-update" not in sys.argv:
        update()
    try:
        from agis.app import main as app_main
        app_main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        log(traceback.format_exc())
        message("AGIS", "AGIS non è riuscito ad avviarsi.\n\nI dettagli sono in:\n"
                f"{LOG}\n\nMandali a Claude in chat per sistemarlo.")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
