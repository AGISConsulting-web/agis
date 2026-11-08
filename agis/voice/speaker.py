"""Parla mentre AGIS scrive: legge ogni frase appena è completa, senza aspettare la fine."""
from __future__ import annotations

import queue
import re
import threading

_SENTENCE_END = re.compile(r"(.+?[.!?…:;])(\s+|$)|(.+?)\n", re.S)


class StreamingSpeaker:
    def __init__(self, tts):
        self.tts = tts
        self._buf = ""
        self._q: queue.Queue = queue.Queue()
        self.spoke_anything = False
        threading.Thread(target=self._worker, daemon=True).start()

    def feed(self, text: str) -> None:
        self._buf += text
        while True:
            m = _SENTENCE_END.match(self._buf)
            # una frase è "completa" solo se dopo c'è già altro testo o un a capo
            if not m or (m.end() == len(self._buf) and not self._buf.endswith(("\n", " "))):
                break
            sentence = (m.group(1) or m.group(3) or "").strip()
            self._buf = self._buf[m.end():]
            if sentence:
                self._q.put(sentence)
                self.spoke_anything = True

    def finish(self, fallback: str = "") -> None:
        rest = self._buf.strip()
        self._buf = ""
        if rest:
            self._q.put(rest)
            self.spoke_anything = True
        elif not self.spoke_anything and fallback:
            self._q.put(fallback)
        self._q.put(None)  # fine: il worker si ferma dopo l'ultima frase

    def cancel(self) -> None:
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass
        self._q.put(None)
        self.tts.stop()

    def _worker(self) -> None:
        while True:
            s = self._q.get()
            if s is None:
                return
            try:
                self.tts.speak(s)
            except Exception as e:  # noqa: BLE001
                print(f"[AGIS] Errore voce: {e}")
