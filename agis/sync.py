"""Sincronizzazione con il cervello condiviso (archivio AGIS su Google Drive).

- pull(): scarica Memoria AGIS, feedback attivi e brief di oggi in
  workspace/memoria/notion.md, che CLAUDE.md importa. Così ogni risposta
  dell'app sa le stesse cose dei task automatici, senza interrogare Drive
  a ogni messaggio (più veloce e consuma meno).
- push_feedback(): carica nel database Feedback AGIS i 👍/👎 dati nell'app.

Il lavoro lo fa Claude Code stesso tramite il connettore Google Drive di claude.ai,
quindi non serve nessuna chiave nell'app.
"""
from __future__ import annotations

import threading
from datetime import date, datetime
from pathlib import Path

from .brain import Brain, BrainError
from .config import NotionConfig
from .memory import Memory

SYSTEM_SYNC = (
    "Sei il modulo di sincronizzazione di AGIS. Esegui solo il compito richiesto usando "
    "gli strumenti di Google Drive. Non fare domande e non aggiungere commenti."
)

MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]


DRIVE_HOWTO = (
    "L'archivio di AGIS è su Google Drive: ogni elemento è un Google Doc e la cartella in cui "
    "si trova è il suo stato. Elenca una cartella con lo strumento di ricerca di Drive "
    "(query \"parentId = '<id>'\"), leggi i documenti con lo strumento di lettura e crea "
    "documenti con create_file (contentMimeType \"text/markdown\", textContent, parentId)."
)


def pull_prompt(cfg: NotionConfig, today: date) -> str:
    return f"""Oggi è il {today.day} {MESI[today.month - 1]} {today.year} ({today.isoformat()}).
{DRIVE_HOWTO}
Leggi da Google Drive e restituisci UN SOLO documento Markdown, senza altro testo prima o dopo, con queste sezioni:

# Memoria AGIS
Il contenuto del Google Doc "🧠 Memoria AGIS" nella cartella {cfg.root_folder}, riportato fedelmente.

# Feedback attivi
I documenti nella cartella {cfg.feedback_active} (attivi) e poi in {cfg.feedback_integrated}
(già integrati), dal più recente. Una riga ciascuno: il titolo del documento (contiene data,
ambito, voto e testo); leggi il contenuto solo se il titolo non basta. Massimo 40 righe.

# Brief di oggi
Nella cartella {cfg.brief_folder}: il documento "Brief · {today.isoformat()} …". Se non c'è, il più
recente, scrivendo "(brief del GG/MM, quello di oggi non è ancora uscito)". Riporta agenda,
meteo, mail e richieste, priorità complete; delle notizie solo i titoli. Se la cartella è vuota
scrivi "Nessun brief ancora".

# Richieste di lavoro aperte
I titoli dei documenti nelle cartelle {cfg.requests_new} (nuove) e {cfg.requests_ready}
(pacchetto pronto), uno per riga. Se non ce ne sono scrivi "Nessuna".

Se una delle fonti non è raggiungibile, scrivi sotto la sua sezione "NON DISPONIBILE" e continua."""


def push_prompt(cfg: NotionConfig, rows: list[tuple]) -> str:
    righe = []
    for _id, ts, rating, note, msg in rows:
        voto = "👍 Utile" if rating > 0 else "👎 Da correggere"
        testo = (note or "").strip() or ("Risposta utile" if rating > 0 else "Risposta da correggere")
        ref = (msg or "").replace("\n", " ").strip()[:300]
        righe.append(f'- Titolo: "{ts[:10]} · App AGIS · {voto.split()[0]} {testo[:120]}" | '
                     f'Feedback: "{testo}" | Voto: {voto} | Risposta di riferimento: "{ref}"')
    elenco = "\n".join(righe)
    return f"""{DRIVE_HOWTO}
Crea {len(rows)} Google Doc nella cartella Drive {cfg.feedback_active} (Feedback attivi), uno per
ciascun elemento qui sotto. Titolo del documento = il Titolo indicato. Contenuto = le righe
"Feedback: …", "Voto: …", "Ambito: App AGIS · Fonte: App AGIS", "Risposta di riferimento: …".

{elenco}

Quando hai finito rispondi esattamente con: OK {len(rows)}
Se non riesci a creare tutti i documenti rispondi con: ERRORE e il motivo."""


class NotionSync:
    def __init__(self, cfg: NotionConfig, brain: Brain, memory: Memory, cache: Path):
        self.cfg = cfg
        self.brain = brain
        self.memory = memory
        self.cache = cache
        self._lock = threading.Lock()  # una sincronizzazione alla volta
        self.last_pull: datetime | None = None

    def pull(self, today: date | None = None) -> bool:
        if not self.cfg.enabled:
            return False
        with self._lock:
            today = today or date.today()
            try:
                reply = self.brain.oneshot(pull_prompt(self.cfg, today), SYSTEM_SYNC)
            except BrainError as e:
                print(f"[AGIS] Sync cervello (Drive) non riuscita: {e}")
                return False
            text = reply.text.strip()
            if reply.is_error or "# Memoria AGIS" not in text:
                print(f"[AGIS] Sync cervello: risposta inattesa: {text[:300]}")
                return False
            if text.count("NON DISPONIBILE") >= 3:
                # Drive non raggiungibile: tieni l'ultima copia buona invece di cancellarla.
                print("[AGIS] Sync cervello: Drive non raggiungibile, tengo la copia precedente")
                return False
            stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
            header = (f"<!-- Copia locale del cervello condiviso (Google Drive), aggiornata il {stamp}. "
                      "Non modificare: viene riscritta a ogni sincronizzazione. -->\n\n")
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            self.cache.write_text(header + text[text.index("# Memoria AGIS"):] + "\n",
                                  encoding="utf-8")
            self.last_pull = datetime.now()
            return True

    def push_feedback(self) -> int:
        """Carica i feedback in sospeso. Restituisce quanti ne ha caricati."""
        if not self.cfg.enabled:
            return 0
        with self._lock:
            rows = self.memory.unsynced_feedback()
            if not rows:
                return 0
            try:
                reply = self.brain.oneshot(push_prompt(self.cfg, rows), SYSTEM_SYNC)
            except BrainError as e:
                print(f"[AGIS] Invio feedback a Drive non riuscito: {e}")
                return 0
            if reply.is_error or f"OK {len(rows)}" not in reply.text:
                print(f"[AGIS] Invio feedback: risposta inattesa: {reply.text[:300]}")
                return 0
            self.memory.mark_synced([r[0] for r in rows])
            return len(rows)
