"""Collega ad AGIS una casella Gmail di lavoro o di scuola.

Uso (dalla cartella agis, con l'ambiente .venv attivo):
    python scripts\\collega_google.py a.loffredo@v-media.it

Si apre il browser: accedi con QUELL'account e consenti. Il token resta sul tuo PC
in data/google/. Ripeti per ogni account. Se un giorno il collegamento scade, rilancia
lo stesso comando.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agis import config as config_mod  # noqa: E402
from agis.google_auth import authorize  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        print("Uso: python scripts\\collega_google.py <email>   (es. a.loffredo@v-media.it)")
        return 1
    email = sys.argv[1].strip().lower()
    cfg = config_mod.load()
    if email not in [a.lower() for a in cfg.google.accounts]:
        print(f"Attenzione: {email} non è nella lista [google] accounts di config.toml.")
        print("Aggiungilo, altrimenti AGIS non lo userà. Continuo comunque con il collegamento.\n")
    try:
        actual = authorize(Path(cfg.google.client_secret), cfg.data_dir, email)
    except Exception as e:  # noqa: BLE001
        print(f"\n❌ Collegamento non riuscito: {e}")
        msg = str(e).lower()
        if "access_denied" in msg or "admin" in msg or "blocked" in msg:
            print("Probabilmente l'amministratore di questo account blocca le app esterne.")
        return 2
    print(f"\n✅ {actual} collegato ad AGIS. Riavvia AGIS per usarlo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
