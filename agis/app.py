"""Applicazione desktop di AGIS: finestra di chat + voce + scorciatoia globale."""
from __future__ import annotations

import json
import threading
import time
import traceback
from pathlib import Path

from . import config as config_mod
from .brain import BrainError
from .live import LiveBrain
from .memory import Memory
from .sync import NotionSync

UI = Path(__file__).resolve().parent / "ui" / "index.html"


class Api:
    """Metodi chiamabili dalla pagina (window.pywebview.api.*)."""

    def __init__(self, cfg: config_mod.Config):
        self._cfg = cfg
        self._memory = Memory(cfg.data_dir / "agis.db",
                             cfg.workspace / "memoria" / "feedback.md")
        allow, deny = cfg.connectors.rules()
        self._brain = LiveBrain(cfg.brain, cfg.workspace, extra_allowed=allow, extra_denied=deny)
        self._sync = NotionSync(cfg.notion, self._brain, self._memory,
                                cfg.workspace / "memoria" / "notion.md")
        self._window = None
        self._busy = threading.Lock()
        self._recorder = self._stt = self._tts = None
        self._speaker = None
        # Accende subito il cervello: il primo messaggio non aspetta l'avvio di Claude Code.
        threading.Thread(target=self._warmup, daemon=True).start()
        if cfg.voice.enabled:
            threading.Thread(target=self._load_voice, daemon=True).start()
        if cfg.notion.enabled:
            threading.Thread(target=self._sync_loop, daemon=True).start()

    def _warmup(self) -> None:
        try:
            self._brain.warmup()
        except BrainError as e:
            self._status(f"⚠️ {e}")

    def _reload_brain(self) -> None:
        """Dopo una sincronizzazione riavvia il cervello (se libero) per fargli rileggere la memoria."""
        if self._busy.acquire(blocking=False):
            try:
                self._brain.stop()
                self._brain.warmup()
            except BrainError as e:
                self._status(f"⚠️ {e}")
            finally:
                self._busy.release()

    # --- cervello condiviso (Notion) ---------------------------------------
    def _sync_loop(self) -> None:
        """All'avvio e poi ogni pull_every_min: invia feedback in sospeso e scarica memoria/brief."""
        while True:
            self._sync_now()
            time.sleep(max(15, self._cfg.notion.pull_every_min) * 60)

    def _sync_now(self) -> None:
        sent = self._sync.push_feedback()
        ok = self._sync.pull()
        if ok:
            self._reload_brain()
            extra = f" · {sent} feedback inviati" if sent else ""
            self._status(f"Cervello aggiornato da Notion alle {time.strftime('%H:%M')}{extra}")
        else:
            self._status("Notion non raggiungibile: uso la memoria locale")

    def sync_notion(self) -> None:
        """Pulsante "Aggiorna" della finestra."""
        self._status("Aggiorno il cervello da Notion…")
        threading.Thread(target=self._sync_now, daemon=True).start()

    # --- voce ---------------------------------------------------------------
    def _load_voice(self) -> None:
        try:
            self._status("Carico la voce…")
            from .voice.recorder import Recorder
            from .voice.stt import SpeechToText
            from .voice.tts import TextToSpeech
            self._recorder = Recorder(self._cfg.voice.sample_rate)
            self._stt = SpeechToText(self._cfg.voice.whisper_model, self._cfg.voice.language)
            self._tts = TextToSpeech(self._cfg.voice.piper_model)
            self._status(f"Pronto · voce {self._tts.engine} · {self._cfg.voice.hotkey} per parlare")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._status(f"Voce non disponibile: {e}")

    def toggle_listening(self) -> None:
        if not self._recorder:
            self._status("La voce non è ancora pronta")
            return
        if self._speaker:
            self._speaker.cancel()
            self._speaker = None
        elif self._tts:
            self._tts.stop()
        if not self._recorder.recording:
            self._recorder.start()
            self._js("setListening(true)")
            self._status("Ti ascolto… premi di nuovo per finire")
            return
        audio = self._recorder.stop()
        self._js("setListening(false)")
        self._status("Trascrivo…")
        text = self._stt.transcribe(audio)
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
            self._memory.add_message("user", text, self._brain.session_id)
            self._status("Penso…")
            self._js("startAgis()")
            speaker = None
            if voice and self._tts:
                from .voice.speaker import StreamingSpeaker
                speaker = self._speaker = StreamingSpeaker(self._tts)
            buf: list[str] = []
            last = [time.monotonic()]

            def flush() -> None:
                if buf:
                    chunk = "".join(buf)
                    buf.clear()
                    self._js(f"appendAgis({json.dumps(chunk)})")
                last[0] = time.monotonic()

            def on_delta(t: str) -> None:
                buf.append(t)
                if speaker:
                    speaker.feed(t)
                if time.monotonic() - last[0] > 0.12:  # aggiorna la finestra ~8 volte al secondo
                    flush()

            try:
                reply = self._brain.ask(text, voice=voice, on_delta=on_delta)
                answer = reply.text
            except BrainError as e:
                answer = f"⚠️ {e}"
            flush()
            if speaker:
                speaker.finish(fallback=answer)
            mid = self._memory.add_message("agis", answer, self._brain.session_id)
            self._js(f"finishAgis({json.dumps(answer)}, {mid})")
            self._status("Pronto")
        finally:
            self._busy.release()

    def feedback(self, message_id: int, rating: int, note: str = "") -> None:
        self._memory.add_feedback(message_id, int(rating), note or "")
        self._status("Feedback salvato: lo userò da ora in poi")
        if self._cfg.notion.enabled:
            def push():
                if self._sync.push_feedback():
                    self._status("Feedback salvato anche su Notion")
            threading.Thread(target=push, daemon=True).start()

    def new_session(self) -> None:
        self._brain.new_session()
        self._status("Nuova conversazione")

    # --- utilità ------------------------------------------------------------
    def _js(self, code: str) -> None:
        if self._window:
            self._window.evaluate_js(code)

    def _status(self, text: str) -> None:
        self._js(f"setStatus({json.dumps(text)})")


def main() -> None:
    import webview

    cfg = config_mod.load()
    api = Api(cfg)
    window = webview.create_window(
        "AGIS", UI.as_uri(), js_api=api, width=460, height=720, min_size=(360, 480))
    api._window = window

    if cfg.voice.enabled:
        try:
            import keyboard
            keyboard.add_hotkey(cfg.voice.hotkey, lambda: threading.Thread(
                target=api.toggle_listening, daemon=True).start())
        except Exception as e:  # noqa: BLE001
            print(f"[AGIS] Scorciatoia globale non attiva: {e}")

    webview.start()
    api._brain.stop()  # finestra chiusa: spegne anche Claude Code


if __name__ == "__main__":
    main()
