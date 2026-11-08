"""Sincronizzazione con il cervello condiviso su Notion.

- pull(): scarica Memoria AGIS, feedback attivi e brief di oggi in
  workspace/memoria/notion.md, che CLAUDE.md importa. Così ogni risposta
  dell'app sa le stesse cose dei task automatici, senza interrogare Notion
  a ogni messaggio (più veloce e consuma meno).
- push_feedback(): carica nel database Feedback AGIS i 👍/👎 dati nell'app.

Il lavoro lo fa Claude Code stesso tramite il server MCP di Notion, quindi non
serve nessun token Notion nell'app.
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
    "gli strumenti Notion. Non fare domande e non aggiungere commenti."
)

MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def pull_prompt(cfg: NotionConfig, today: date) -> str:
    return f"""Oggi è il {today.day} {MESI[today.month - 1]} {today.year} ({today.isoformat()}).
Leggi da Notion e restituisci UN SOLO documento Markdown, senza altro testo prima o dopo, con queste sezioni:

# Memoria AGIS
Il contenuto della pagina {cfg.memoria_page}, riportato fedelmente (puoi togliere solo righe vuote).

# Feedback attivi
Dal database {cfg.feedback_ds}: tutte le righe con Stato "Attivo" o "Integrato nelle istruzioni",
dalla più recente. Una riga ciascuna: "- AAAA-MM-GG [Ambito] Voto — Feedback". Massimo 40 righe.

# Brief di oggi
Dal database {cfg.brief_ds}: la pagina con Data di oggi. Se non c'è, la più recente,
scrivendo "(brief del GG/MM, quello di oggi non è ancora uscito)". Riporta titolo, Priorità
e il contenuto della pagina, riassumendo solo se supera circa 80 righe (agenda, meteo e
priorità vanno sempre riportati completi). Se il database è vuoto scrivi "Nessun brief ancora".

Se una delle fonti non è raggiungibile, scrivi sotto la sua sezione "NON DISPONIBILE" e continua."""


def push_prompt(cfg: NotionConfig, rows: list[tuple]) -> str:
    righe = []
    for _id, ts, rating, note, msg in rows:
        voto = "👍 Utile" if rating > 0 else "👎 Da correggere"
        testo = (note or "").strip() or ("Risposta utile" if rating > 0 else "Risposta da correggere")
        ref = (msg or "").replace("\n", " ").strip()[:300]
        righe.append(f'- Feedback: "{testo}" | Voto: {voto} | Data: {ts[:10]} | '
                     f'Risposta di riferimento: "{ref}"')
    elenco = "\n".join(righe)
    return f"""Crea {len(rows)} righe nel database Notion {cfg.feedback_ds}, una per ciascun elemento qui sotto.
Per tutte: Ambito = "App AGIS", Fonte = "App AGIS", Stato = "Attivo".
Usa esattamente i testi indicati per Feedback, Voto, Data e Risposta di riferimento.

{elenco}

Quando hai finito rispondi esattamente con: OK {len(rows)}
Se non riesci a creare tutte le righe rispondi con: ERRORE e il motivo."""


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
                print(f"[AGIS] Sync Notion non riuscita: {e}")
                return False
            text = reply.text.strip()
            if reply.is_error or "# Memoria AGIS" not in text:
                print(f"[AGIS] Sync Notion: risposta inattesa: {text[:300]}")
                return False
            if text.count("NON DISPONIBILE") >= 3:
                # Notion non raggiungibile: tieni l'ultima copia buona invece di cancellarla.
                print("[AGIS] Sync Notion: Notion non raggiungibile, tengo la copia precedente")
                return False
            stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
            header = (f"<!-- Copia locale del cervello condiviso su Notion, aggiornata il {stamp}. "
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
                print(f"[AGIS] Invio feedback a Notion non riuscito: {e}")
                return 0
            if reply.is_error or f"OK {len(rows)}" not in reply.text:
                print(f"[AGIS] Invio feedback: risposta inattesa: {reply.text[:300]}")
                return 0
            self.memory.mark_synced([r[0] for r in rows])
            return len(rows)
