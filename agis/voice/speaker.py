"""Parla mentre AGIS scrive.

Con la voce, AGIS risponde in due parti:

    🗣️ due o tre frasi parlate, come una persona che spiega in breve
    ---
    il messaggio scritto completo (passaggi, nomi di file, link…)

`VoiceSplitter` manda la prima parte all'altoparlante e la seconda alla finestra.
Se AGIS non usa questo formato, si legge al massimo l'inizio della risposta e si
rimanda al testo scritto: mai più minuti di percorsi e codici letti ad alta voce.
"""
from __future__ import annotations

import queue
import re
import threading

_SENTENCE_END = re.compile(r"(.+?[.!?…:;])(\s+|$)|(.+?)\n", re.S)
SPOKEN_MARK = "🗣️"
SEPARATOR = re.compile(r"^\s*---+\s*$", re.M)
MAX_FALLBACK_SENTENCES = 3


_MARK_RE = re.compile(r"^[\U0001F5E3\uFE0F\s]+")
_PENDING_DASHES = re.compile(r"\n[ \t]*-*[ \t]*$")


def split_voice_reply(text: str) -> tuple[str, str]:
    """(parte parlata, parte scritta). Senza formato: ("", testo intero)."""
    stripped = text.lstrip()
    if not stripped.startswith(SPOKEN_MARK[0]):
        return "", text
    m = SEPARATOR.search(stripped)
    if not m:
        return _MARK_RE.sub("", stripped), ""
    return _MARK_RE.sub("", stripped[:m.start()]).strip(), stripped[m.end():].strip()


class VoiceSplitter:
    """Smista il testo in arrivo: parlato → altoparlante, scritto → finestra."""

    def __init__(self, speaker: "StreamingSpeaker"):
        self.speaker = speaker
        self._raw = ""
        self._mode = "?"   # "?" ancora da capire · "spoken" · "written" · "plain"
        self._shown = 0    # quanta parte scritta è già stata mandata alla finestra

    def feed(self, chunk: str) -> str:
        """Riceve un pezzo di risposta, restituisce il testo nuovo da mostrare."""
        self._raw += chunk
        if self._mode == "?":
            head = self._raw.lstrip()
            if not head:
                return ""
            if head.startswith(SPOKEN_MARK[0]):
                self._mode = "spoken"
                self._spoken_sent = 0
            else:
                self._mode = "plain"
                self.speaker.max_sentences = MAX_FALLBACK_SENTENCES
        if self._mode == "plain":
            self.speaker.feed(chunk)
            new, self._shown = self._raw[self._shown:], len(self._raw)
            return new
        spoken, written = split_voice_reply(self._raw)
        if self._mode == "spoken":
            if SEPARATOR.search(self._raw):
                self.speaker.feed(spoken[self._spoken_sent:] + "\n")
                self._spoken_sent = len(spoken)
                self._mode = "written"
            else:
                # non leggere un eventuale "---" ancora a metà
                pm = _PENDING_DASHES.search(spoken)
                cut = spoken[:pm.start() + 1] if pm else spoken
                if len(cut) > self._spoken_sent:
                    self.speaker.feed(cut[self._spoken_sent:])
                    self._spoken_sent = len(cut)
                return ""
        new, self._shown = written[self._shown:], len(written)
        return new

    def written(self, final_text: str) -> str:
        spoken, written = split_voice_reply(final_text)
        return written or spoken or final_text


class StreamingSpeaker:
    def __init__(self, tts, max_sentences: int | None = None):
        self.tts = tts
        self.max_sentences = max_sentences
        self._buf = ""
        self._count = 0
        self._text_q: queue.Queue = queue.Queue()
        self._audio_q: queue.Queue = queue.Queue(maxsize=2)
        self._cancelled = False
        self.spoke_anything = False
        threading.Thread(target=self._synth_worker, daemon=True).start()
        threading.Thread(target=self._play_worker, daemon=True).start()

    def _put(self, sentence: str) -> None:
        if self.max_sentences is not None and self._count >= self.max_sentences:
            if self._count == self.max_sentences:
                self._text_q.put("Il resto te l'ho scritto.")
                self._count += 1
            return
        self._text_q.put(sentence)
        self._count += 1
        self.spoke_anything = True

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
                self._put(sentence)

    def finish(self, fallback: str = "") -> None:
        rest = self._buf.strip()
        self._buf = ""
        if rest:
            self._put(rest)
        elif not self.spoke_anything and fallback:
            self._put(fallback)
        self._text_q.put(None)  # fine: i worker si fermano dopo l'ultima frase

    def cancel(self) -> None:
        self._cancelled = True
        for q in (self._text_q, self._audio_q):
            try:
                while True:
                    q.get_nowait()
            except queue.Empty:
                pass
        self._text_q.put(None)
        self.tts.stop()

    def _synth_worker(self) -> None:
        while True:
            s = self._text_q.get()
            if s is None or self._cancelled:
                self._audio_q.put(None)
                return
            try:
                self._audio_q.put(self.tts.synth(s))
            except Exception as e:  # noqa: BLE001
                print(f"[AGIS] Errore voce: {e}")

    def _play_worker(self) -> None:
        while True:
            item = self._audio_q.get()
            if item is None or self._cancelled:
                return
            try:
                self.tts.play(item)
            except Exception as e:  # noqa: BLE001
                print(f"[AGIS] Errore voce: {e}")
