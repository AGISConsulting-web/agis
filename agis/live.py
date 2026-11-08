"""Cervello "sempre acceso": un solo processo Claude Code per tutta la conversazione.

Prima AGIS avviava `claude -p` a ogni messaggio: ogni volta Claude Code ripartiva da
zero e si ricollegava a tutti i connettori (Gmail, Calendar, Drive, Notion…), e la
risposta arrivava solo alla fine. Qui il processo resta acceso (modalità stream-json):
i connettori si collegano una volta sola e il testo arriva mentre viene scritto.
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from .brain import Brain, BrainError, Reply

VOICE_TAG = "[VOCE]"
LIVE_SYSTEM = (
    "La conversazione avviene in una finestra di chat: puoi usare markdown leggero. "
    f"Quando un messaggio inizia con {VOICE_TAG}, la tua risposta verra letta ad alta voce: "
    "frasi brevi e naturali, niente elenchi, tabelle, markdown, emoji o link, al massimo "
    "4 o 5 frasi, poi chiedi se vuole i dettagli. Il tag non va ripetuto nella risposta."
)


class LiveBrain(Brain):
    """Stessa configurazione di Brain, ma la chat usa un processo persistente.

    `oneshot()` (sincronizzazione Notion) resta quello di Brain: gira a parte.
    """

    def __init__(self, *args, popen: Callable[..., subprocess.Popen] = subprocess.Popen, **kw):
        super().__init__(*args, **kw)
        self._popen = popen
        self._proc: subprocess.Popen | None = None
        self._events: queue.Queue = queue.Queue()
        self._lock = threading.Lock()  # un messaggio alla volta

    # --- processo -------------------------------------------------------------
    def live_command(self) -> list[str]:
        cmd = self.build_command(False, resume=True, system=LIVE_SYSTEM)
        i = cmd.index("--output-format")
        cmd[i:i + 2] = ["--input-format", "stream-json", "--output-format", "stream-json",
                        "--verbose", "--include-partial-messages"]
        return cmd

    def _start(self) -> None:
        kw = {}
        if sys.platform == "win32":
            kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW: nessuna finestra nera
        try:
            self._proc = self._popen(
                self.live_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
                cwd=str(self.workspace), env=self._env(), **kw)
        except FileNotFoundError as e:
            raise BrainError("Claude Code non trovato. Installalo e fai il login, oppure "
                             "imposta claude_cmd in config.toml.") from e
        self._events = queue.Queue()
        proc, events = self._proc, self._events
        threading.Thread(target=self._read, args=(proc, events), daemon=True).start()
        threading.Thread(target=self._drain_stderr, args=(proc,), daemon=True).start()

    @staticmethod
    def _read(proc, events: queue.Queue) -> None:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                events.put(json.loads(line))
            except json.JSONDecodeError:
                continue
        events.put({"type": "_eof"})

    @staticmethod
    def _drain_stderr(proc) -> None:
        if proc.stderr:
            for line in proc.stderr:
                if line.strip():
                    print(f"[claude] {line.rstrip()}")

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def warmup(self) -> None:
        """Avvia il processo in anticipo, così il primo messaggio non aspetta l'avvio."""
        with self._lock:
            if not self._alive():
                self._start()

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc and proc.poll() is None:
            try:
                proc.stdin.close()
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                proc.kill()

    def new_session(self) -> None:
        super().new_session()
        self.stop()

    # --- conversazione ----------------------------------------------------------
    def ask(self, prompt: str, voice: bool = False,
            on_delta: Callable[[str], None] | None = None) -> Reply:
        text = f"{VOICE_TAG} {prompt}" if voice else prompt
        with self._lock:
            for attempt in (1, 2):
                if not self._alive():
                    self._start()  # con --resume riprende la conversazione se era caduta
                try:
                    return self._turn(text, on_delta)
                except _ProcessDied:
                    self.stop()
                    if attempt == 2:
                        raise BrainError("Claude Code si è chiuso inaspettatamente. "
                                         "Riprova; se succede ancora controlla il login.")
        raise BrainError("errore inatteso")  # pragma: no cover

    def _turn(self, text: str, on_delta) -> Reply:
        msg = {"type": "user", "message": {"role": "user", "content": text}}
        try:
            self._proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as e:
            raise _ProcessDied() from e
        deadline = time.monotonic() + self.cfg.timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.stop()
                raise BrainError("Claude Code non ha risposto in tempo.")
            try:
                ev = self._events.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                continue
            kind = ev.get("type")
            if kind == "_eof":
                raise _ProcessDied()
            if kind == "stream_event" and on_delta:
                e = ev.get("event", {})
                d = e.get("delta", {})
                if e.get("type") == "content_block_delta" and d.get("type") == "text_delta":
                    on_delta(d.get("text", ""))
            elif kind == "result":
                sid = ev.get("session_id")
                if sid:
                    self.session_id = sid
                result = ev.get("result") or ""
                is_error = bool(ev.get("is_error"))
                if is_error and not result:
                    result = "Errore durante la risposta: " + str(ev.get("subtype", ""))
                return Reply(text=result, session_id=sid, is_error=is_error)


class _ProcessDied(Exception):
    pass
