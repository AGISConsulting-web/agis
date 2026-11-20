"""Crea l'icona di AGIS sul desktop e nel menu Start (Windows). Va lanciato UNA volta.

Uso (dalla cartella agis, con l'ambiente .venv attivo):
    python scripts\\crea_collegamento.py
    python scripts\\crea_collegamento.py --avvio-automatico   # parte anche all'accensione del PC
    python scripts\\crea_collegamento.py --rimuovi             # toglie tutte le icone
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICON = ROOT / "assets" / "agis.ico"


def ps(script: str) -> str:
    res = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or res.stdout.strip())
    return res.stdout.strip()


def folder(name: str) -> Path:
    # Desktop / Programs (menu Start) / Startup, anche se il desktop è dentro OneDrive
    return Path(ps(f"[Environment]::GetFolderPath('{name}')"))


def make_shortcut(dest: Path, pythonw: Path) -> None:
    q = lambda p: str(p).replace("'", "''")  # noqa: E731
    ps(f"""$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{q(dest)}')
$s.TargetPath = '{q(pythonw)}'
$s.Arguments = '-m agis.launcher'
$s.WorkingDirectory = '{q(ROOT)}'
$s.IconLocation = '{q(ICON)},0'
$s.Description = 'AGIS - il tuo assistente'
$s.Save()""")


def main() -> int:
    if sys.platform != "win32":
        print("Questo script è per Windows.")
        return 1
    places = {"Desktop": folder("Desktop"), "menu Start": folder("Programs")}
    if "--avvio-automatico" in sys.argv:
        places["avvio automatico"] = folder("Startup")
    if "--rimuovi" in sys.argv:
        for where in ("Desktop", "Programs", "Startup"):
            f = folder(where) / "AGIS.lnk"
            if f.exists():
                f.unlink()
                print(f"Tolta l'icona da {f.parent}")
        return 0

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if ".venv" not in str(pythonw):
        print("⚠️ Attiva prima l'ambiente: .venv\\Scripts\\activate  e poi rilancia questo comando.")
        return 1
    if not pythonw.exists():
        print(f"Non trovo {pythonw}.")
        return 1
    for name, path in places.items():
        path.mkdir(parents=True, exist_ok=True)
        make_shortcut(path / "AGIS.lnk", pythonw)
        print(f"✅ Icona AGIS creata: {name}")
    print("\nDa ora apri AGIS con un doppio clic sull'icona. Puoi chiudere PowerShell.")
    print("Per tenerlo nella barra delle applicazioni: apri AGIS, tasto destro sulla sua icona "
          "in basso → Aggiungi alla barra delle applicazioni.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
