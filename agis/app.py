"""Applicazione desktop di AGIS: finestra di chat + voce + scorciatoia globale."""
from __future__ import annotations

import json
import threading
import traceback
from pathlib import Path

from . import config as config_mod
from .brain import Brain, BrainError
from .memory import Memory

UI = Path(__file__).resolve().parent / "ui" / "index.html"


class Api:
    """Metodi chiamabili dalla pagina (window.pywebview.api.*)."""

    def __init__(self, cfg: config_mod.Config):
        self.cfg = cfg
        self.memory = Memory(cfg.data_dir / "agis.db",
                             cfg.workspace / "memoria" / "feedback.md")
        self.brain = Brain(cfg.brain, cfg.workspace)
        self.window = None
        self._busy = threading.Lock()
        self.recorder = self.stt = self.tts = None
        if cfg.voice.enabled:
            threading.Thread(target=self._load_voice, daemon=True).start()

    # --- voce ---------------------------------------------------------------
    def _load_voice(self) -> None:
        try:
            self._status("Carico la voce…")
            from .voice.recorder import Recorder
            from .voice.stt import SpeechToText
            from .voice.tts import TextToSpeech
            self.recorder = Recorder(self.cfg.voice.sample_rate)
            self.stt = SpeechToText(self.cfg.voice.whisper_model, self.cfg.voice.language)
            self.tts = TextToSpeech(self.cfg.voice.piper_model)
            self._status(f"Pronto · voce {self.tts.engine} · {self.cfg.voice.hotkey} per parlare")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._status(f"Voce non disponibile: {e}")

    def toggle_listening(self) -> None:
        if not self.recorder:
            self._status("La voce non è ancora pronta")
            return
        if self.tts:
            self.tts.stop()
        if not self.recorder.recording:
            self.recorder.start()
            self._js("setListening(true)")
            self._status("Ti ascolto… premi di nuovo per finire")
            return
        audio = self.recorder.stop()
        self._js("setListening(false)")
        self._status("Trascrivo…")
        text = self.stt.transcribe(audio)
        if not text:
            self._status("Non ho sentito niente")
            return
        self._js(f"addMessage('user', {json.dumps(text)}, null)")
        self._answer(text, voice=True)

    # --- chat ---------------------------------------------------------------
    def send(self, text: str) -> None:
        text = (text or "").strip()
        if text:
            threading.Thread(target=self._answer, args=(text, False), daemon=True).start()

    def _answer(self, text: str, voice: bool) -> None:
        if not self._busy.acquire(blocking=False):
            self._status("Sto ancora pensando alla richiesta precedente")
            return
        try:
            self.memory.add_message("user", text, self.brain.session_id)
            self._status("Penso…")
            try:
                reply = self.brain.ask(text, voice=voice)
                answer = reply.text
            except BrainError as e:
                answer = f"⚠️ {e}"
            mid = self.memory.add_message("agis", answer, self.brain.session_id)
            self._js(f"addMessage('agis', {json.dumps(answer)}, {mid})")
            self._status("Pronto")
            if voice and self.tts:
                self.tts.speak(answer)
        finally:
            self._busy.release()

    def feedback(self, message_id: int, rating: int, note: str = "") -> None:
        self.memory.add_feedback(message_id, int(rating), note or "")
        self._status("Feedback salvato: lo userò da ora in poi")

    def new_session(self) -> None:
        self.brain.new_session()
        self._status("Nuova conversazione")

    # --- utilità ------------------------------------------------------------
    def _js(self, code: str) -> None:
        if self.window:
            self.window.evaluate_js(code)

    def _status(self, text: str) -> None:
        self._js(f"setStatus({json.dumps(text)})")


def main() -> None:
    import webview

    cfg = config_mod.load()
    api = Api(cfg)
    window = webview.create_window(
        "AGIS", UI.as_uri(), js_api=api, width=460, height=720, min_size=(360, 480))
    api.window = window

    if cfg.voice.enabled:
        try:
            import keyboard
            keyboard.add_hotkey(cfg.voice.hotkey, lambda: threading.Thread(
                target=api.toggle_listening, daemon=True).start())
        except Exception as e:  # noqa: BLE001
            print(f"[AGIS] Scorciatoia globale non attiva: {e}")

    webview.start()


if __name__ == "__main__":
    main()
